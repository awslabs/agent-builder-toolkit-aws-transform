# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A2UI surfaces for the AWS Transform chat UI.

Builds the ``atx-a2ui`` fenced block that the AWS Transform web app renders as an
interactive surface in chat: tables, forms, charts, side panels. A surface is the
A2UI v0.9 three-message array (createSurface, updateComponents, updateDataModel)
for the ``atx-hitl/v1`` component catalog, which ships with the ``a2ui-rendering``
platform skill.

Usage:

    from agent_builder_sdk.ui_chat.a2ui import build_a2ui_block

    block = build_a2ui_block(
        "migration-preferences",
        {"component": "SpaceBetween", "children": [
            {"component": "FormField", "label": "Target region", "children": [
                {"component": "Input", "value": {"path": "/form/region"}}]},
            {"component": "SubmitButton", "children": "Submit"},
        ]},
        {"form": {"region": ""}},
    )
    message_text = f"Pick a target region.\\n\\n{block}"

For an agent that returns an A2A task instead, put ``build_a2ui_messages(...)`` in
the task artifact metadata under ``A2UI_EXTENSION_KEY``.

Both raise ``A2UIValidationError`` listing every problem found, so the caller, or an
agent through the ``render_a2ui_surface`` tool, can fix them all in one pass.
"""

import itertools
import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any, Optional

from strands import tool

from agent_builder_sdk.util.suggestions_manager import add_suggestions

BLOCK_TAG = "atx-a2ui"
CATALOG_ID = "atx-hitl/v1"
VERSION = "v0.9"
A2UI_EXTENSION_KEY = "https://a2ui.org/a2a-extension/a2ui/v0.9"
CATALOG_PATH = (
    Path(__file__).parent.parent / "platform_skills" / "a2ui-rendering" / "references" / "catalog.json"
)
# Array props whose items point at a component subtree through `contentId`.
_ITEM_CONTENT_PROPS = {"tabs", "steps"}
_ARRAY_TYPES = ("array", "DynamicValue", "DataBinding")
# The keys of a nested list in a catalog key list, e.g. "[{header?: string, field: string}]".
_NESTED_KEYS = re.compile(r"(\w+\??): *([^,}]+)")
_MISSING = object()


class A2UIValidationError(ValueError):
    """A surface the web app would not render. ``issues`` lists every problem found."""

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


@cache
def load_catalog() -> dict:
    """The ``atx-hitl/v1`` catalog: components, their props, platform actions, functions."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _has(value: Any, key: str) -> bool:
    """``value`` is an object with a string under ``key``, e.g. a ``component`` name, a ``path`` binding or a function ``call``."""
    return isinstance(value, dict) and isinstance(value.get(key), str)


def _is_list(value: Any) -> bool:
    """An array. JSON writes a tuple from a Python caller as an array too."""
    return isinstance(value, (list, tuple))


def _spec(specs: dict, node: Any) -> dict:
    """The catalog entry of the component ``node`` names. Empty when the name is missing, not a string or unknown."""
    return specs.get(node["component"], {}) if _has(node, "component") else {}


def _is_template(value: Any) -> bool:
    """A list template: ``{"componentId", "path"}`` in a ChildList prop repeats one component over an array."""
    return _has(value, "componentId") and _has(value, "path")


def _is_data(prop_spec: dict, value: Any) -> bool:
    """A literal list in a DynamicValue prop (rows, series, tokens) is data: no child components, no bindings."""
    return _is_list(value) and "DynamicValue" in str(prop_spec.get("type"))


def _dicts(value: Any) -> Iterator[dict]:
    """Every dict nested in ``value``. An action ``context`` maps free names to values, so only its values count."""
    if isinstance(value, dict):
        yield value
        value = [list(v.values()) if k == "context" and isinstance(v, dict) else v for k, v in value.items()]
    if _is_list(value):
        for item in value:
            yield from _dicts(item)


def flatten(component_tree: dict) -> list[dict]:
    """Turn one nested component tree into the flat A2UI adjacency list.

    Child components nested in a prop, or in ``tabs``/``steps`` items as ``content``, become
    ID references. Inline rows of a DynamicValue prop such as ``Table.items`` stay data. The
    root gets ID ``root`` and comes first; other components keep their ``id`` or get a generated
    one. A tab or step with no ``id`` gets the ID of its content.
    """
    flat: list[dict] = []
    counter = itertools.count(1)
    specs = load_catalog()["components"]
    # A generated ID must not repeat an explicit one, wherever that one is in the tree.
    taken = {d["id"] for d in _dicts(component_tree) if _has(d, "id")}

    def visit(node: dict, cid: str) -> str:
        out: dict = {"id": cid}
        flat.append(out)
        props = _spec(specs, node).get("props", {})
        for key, value in node.items():
            if key != "id":
                out[key] = value if _is_data(props.get(key, {}), value) else convert(key, value)
        return cid

    def child(node: dict) -> str:
        generated = (f"{node['component'].lower()}-{n}" for n in counter)
        cid = node["id"] if _has(node, "id") else None
        return visit(node, cid or next(i for i in generated if i not in taken))

    def convert(key: str, value: Any) -> Any:
        if _has(value, "component"):
            return [child(value)]
        if not _is_list(value):
            return value
        items = []
        for item in value:
            if _has(item, "component"):
                item = child(item)
            elif key in _ITEM_CONTENT_PROPS and isinstance(item, dict) and _has(item.get("content"), "component"):
                content = item["content"]
                item = {k: v for k, v in item.items() if k != "content"}
                item["contentId"] = child(content)
                item.setdefault("id", item["contentId"])
            items.append(item)
        return items

    visit(component_tree, "root")
    return flat


def _lookup(model: Any, path: str) -> Any:
    """The data-model value at an absolute ``path``, or ``_MISSING``. An array index is ASCII digits only."""
    for part in path.strip("/").split("/"):
        if isinstance(model, dict) and part in model:
            model = model[part]
        elif _is_list(model) and part.isascii() and part.isdigit() and int(part) < len(model):
            model = model[int(part)]
        else:
            return _MISSING
    return model


def _rows(value: Any, data_model: Any) -> Any:
    """The rows of an array prop: its literal value, or what its binding names in the data model."""
    if _has(value, "path"):
        return _lookup(data_model, value["path"]) if value["path"].startswith("/") else _MISSING
    return value


def _wanted(kind: str, value: Any) -> Optional[str]:
    """What this catalog type takes, when ``value`` has another form. None: it fits, or the type has no check."""
    is_list, bound = _is_list(value), _has(value, "path")
    text = bound or _has(value, "call") or not (is_list or isinstance(value, dict))
    # flatten() has turned nested components into a list of IDs.
    children = is_list or _is_template(value)
    binds = "DynamicValue" in kind or "DataBinding" in kind
    forms = [  # (the type takes this form, what to give, the value has this form)
        ("DynamicString" in kind, 'text or a binding like {"path": "/data/title"}', text),
        ("ChildList" in kind, 'a list of components like [{"component": "TextContent", "children": "..."}]', children),
        ("array" in kind or (binds and kind != "DataBinding"), "an array", is_list or bound),
        (binds, 'a binding like {"path": "/data/items"}', is_list or bound),
        (kind in ("boolean", "DynamicBoolean"), "true or false, without quotes", text and not isinstance(value, str)),
        (kind in ("number", "DynamicNumber"), "a number, without quotes", text and not isinstance(value, str)),
        (kind == "string", "text", text),
    ]
    allowed = [(want, fits) for takes, want, fits in forms if takes]
    return None if any(fits for _, fits in allowed) else " or ".join(want for want, _ in allowed) or None


def _value_issues(where: str, spec: dict, value: Any) -> list[str]:
    """A wrong form of ``value``, or a literal outside ``values``, against the catalog spec of a prop or an item key."""
    want = _wanted(str(spec.get("type")), value)
    if want:
        form = {str: "a string", list: "a component or a list", dict: "an object"}.get(type(value))
        return [f"{where} is {form or json.dumps(value, default=str)}; give {want}"]
    if "values" in spec and not (_has(value, "path") or _has(value, "call")) and value not in spec["values"]:
        return [f"{where} must be one of {', '.join(map(json.dumps, spec['values']))}"]
    return []


def _key_issues(where: str, keys: dict, obj: Any, data: bool = False) -> list[str]:
    """Problems in one object against its catalog key list, e.g. a Table column: unknown keys, missing keys, wrong forms.

    The catalog is the contract, so a key it does not name is an error: a column with `key` instead
    of `field` renders as an empty column. The catalog gives a key as text or, like a prop, as a spec.
    A text key is optional when its entry ends in "?", says "optional" or "default", or is a list
    "[...]"; a spec key is optional unless it says ``required``.
    A row from the data model (``data``) may have more keys.
    """
    allowed, required, string_keys, nested_lists, key_specs = set(), set(), {}, {}, {}
    for k, v in keys.items():
        name = k.rstrip("?")
        allowed.add(name)
        if isinstance(v, dict):
            key_specs[name] = v
            kind, optional = str(v.get("type")), not v.get("required")
        else:
            kind, low = v, v.lower()
            optional = k.endswith("?") or low.startswith("[") or "optional" in low or "default" in low
            if kind.startswith("string"):
                string_keys[name] = kind
        if kind.startswith("[{"):
            nested_lists[name] = dict(_NESTED_KEYS.findall(kind))
        if not optional:
            required.add(name)
    if not isinstance(obj, dict):
        return [f"{where} must be an object with keys {', '.join(sorted(allowed))}"]
    unknown, missing = (set() if data else obj.keys() - allowed), required - obj.keys()
    issues = []
    if "content" in unknown and "contentId" in missing:
        # A tab or step in the nested form: flatten() moves `content` to `contentId` only when it is one component.
        issues.append(f'{where}.content must be one component, e.g. {{"component": "SpaceBetween", "children": [...]}}')
        unknown, missing = unknown - {"content"}, missing - {"contentId", "id"}
    issues += [f"{where} has no key '{k}' (allowed: {', '.join(sorted(allowed))})" for k in sorted(unknown, key=str)]
    issues += [f"{where} is missing '{k}'" for k in sorted(missing)]
    issues += [f"{where}.{k} must be a string. Catalog: {v}" for k, v in string_keys.items() if isinstance(obj.get(k), dict) or _is_list(obj.get(k))]
    for k, spec in key_specs.items():
        if obj.get(k) is not None:
            issues += _value_issues(f"{where}.{k}", spec, obj[k])
    for k, inner_keys in nested_lists.items():
        if obj.get(k) is not None:
            issues += _item_issues(f"{where}.{k}", inner_keys, obj[k], data, first=True)
    return issues


def _item_issues(where: str, keys: dict, items: Any, data: bool = False, first: bool = False) -> list[str]:
    """``_key_issues`` for each object of a list, e.g. Table columnDefinitions."""
    if not _is_list(items):
        return [f"{where} must be an array of objects with keys {', '.join(sorted(k.rstrip('?') for k in keys))}"]
    found = (_key_issues(f"{where}[{i}]", keys, item, data) for i, item in enumerate(items))
    # Data rows and nested lists such as chart points repeat one shape: the first item with a problem stands for the rest.
    return next(filter(None, found), []) if data or first else [issue for issues in found for issue in issues]


def _array_issues(where: str, prop: str, prop_spec: dict, value: Any, data_model: Any) -> list[str]:
    """Problems in the rows of an array prop: its literal list, or the list its binding names in the data model."""
    rows, bound = _rows(value, data_model), _has(value, "path")
    # A single selection is one ID or row, not an array. A bound array may start as null.
    if prop == "selectedItems" or rows is None or rows is _MISSING:
        return []
    if not _is_list(rows):
        return [f"{where} is bound to '{value['path']}', which is not an array in data_model; bind an array ([] when empty)"] if bound else []
    if isinstance(prop_spec.get("items"), dict):
        return _item_issues(where, prop_spec["items"], rows, bound)
    if prop_spec.get("type") == "DynamicValue" and not all(isinstance(row, dict) for row in rows):
        return [f"{where} rows must be objects with named fields. Catalog: {prop_spec.get('description', 'see the prop')}"]
    return []


def _field_issues(where: str, c: dict, rows: Any) -> list[str]:
    """Row fields that Table columns and Cards sections name but no row has: those cells render blank."""
    card = c.get("cardDefinition")
    names = [d["field"] for d in _dicts([c.get("columnDefinitions"), card]) if _has(d, "field")]
    names += [card["header"]] if _has(card, "header") else []
    if not (names and _is_list(rows) and rows and all(isinstance(row, dict) for row in rows)):
        return []
    keys = sorted({str(k) for row in rows for k in row})
    near = {re.sub(r"[\W_]", "", k).lower(): k for k in keys}
    missing = {name: near.get(re.sub(r"[\W_]", "", name).lower()) for name in names if name not in keys}
    # One unmatched name can be an optional column that is empty in this data, so it is reported
    # only when no name matches (every cell is blank) or a row key differs from it by case or punctuation.
    return [
        f"{where} field '{name}' is not a key of any row (row keys: {', '.join(keys)})"
        + (f"; did you mean '{hint}'?" if hint else "")
        for name, hint in missing.items()
        if hint or len(missing) == len(set(names))
    ]


def validate(components: list[dict], data_model: dict) -> list[str]:
    """Every catalog and protocol problem in a flat surface, or [] when it will render."""
    catalog = load_catalog()
    specs, universal = catalog["components"], catalog.get("universalProps", {})
    functions = {name for group in catalog.get("functions", {}).values() for name in group}
    issues = []
    ids = [c.get("id") for c in components]
    if not ids or ids[0] != "root":
        issues.append("the first component must have id 'root'")
    issues += [f"duplicate component id '{d}'" for d in sorted({str(i) for i in ids if ids.count(i) > 1})]
    # A reference is a string, so only a string ID can be its target.
    known, paths, calls = {i for i in ids if isinstance(i, str)}, set(), set()

    for c in components:
        cid, name = c.get("id"), c.get("component")
        spec = _spec(specs, c)
        props = spec.get("props", {})
        for d in _dicts([value for prop, value in c.items() if not _is_data(props.get(prop, {}), value)]):
            if _has(d, "path"):
                paths.add(d["path"])
            if _has(d, "call"):
                calls.add(d["call"])
        if not spec:
            issues.append(f"{cid}: unknown component '{name}'; see references/catalog.json")
            continue
        for prop in sorted(c.keys() - props.keys() - universal.keys() - {"id", "component"}, key=str):
            issues.append(f"{cid}: {name} has no prop '{prop}' (allowed: {', '.join(sorted(props))})")
        for prop, prop_spec in {**universal, **props}.items():
            value, kind, where = c.get(prop), str(prop_spec.get("type")), f"{cid}: {name}.{prop}"
            if value is None:
                if prop_spec.get("required"):
                    issues.append(f"{cid}: {name} is missing required prop '{prop}'")
                continue
            issues += _value_issues(where, prop_spec, value)
            if "ChildList" in kind:
                # The value names components by ID: each entry of a list, or the `componentId` of a list template.
                entries = [value["componentId"]] if _is_template(value) else value if _is_list(value) else []
                refs = [ref for ref in entries if isinstance(ref, str)]
                issues += [f"{cid}: '{prop}' references unknown component '{ref}'" for ref in refs if ref not in known]
                if len(refs) < len(entries):
                    issues.append(f'{where} takes components: each entry is an object with a "component" name')
            if any(t in kind for t in _ARRAY_TYPES):
                issues += _array_issues(where, prop, prop_spec, value, data_model)
            if isinstance(prop_spec.get("properties"), dict):
                issues += _key_issues(where, prop_spec["properties"], value)
        issues += _field_issues(f"{cid}: {name}", c, _rows(c.get("items"), data_model))
        for prop in sorted(_ITEM_CONTENT_PROPS & c.keys()):
            items = c[prop] if _is_list(c[prop]) else []
            refs = [i["contentId"] for i in items if isinstance(i, dict) and "contentId" in i]
            # A `contentId` that is a list or an object is reported with the item keys, as not a string.
            unknown = [r for r in refs if not (isinstance(r, dict) or _is_list(r) or r in known)]
            issues += [f"{cid}: '{prop}' references unknown component '{r}'" for r in unknown]

    if "\u00a0" in json.dumps(components, ensure_ascii=False):
        issues.append("replace non-breaking spaces (U+00A0) with ordinary spaces")
    issues += [f"unknown function '{f}' (catalog functions: {', '.join(sorted(functions))})" for f in sorted(calls - functions)]
    # Inside a {"componentId", "path"} template, a path with no leading "/" is relative to the current array item.
    template = any(_has(value, "componentId") for c in components for value in c.values())
    for path in sorted(paths):
        if not path.startswith("/"):
            if not template:
                issues.append(f"bound path '{path}' must start with '/' and use '/' between keys, e.g. '/data/items'")
        # "__" segments are renderer-owned state (e.g. /__showValidation), not agent data.
        elif not any(p.startswith("__") for p in path.split("/")) and _lookup(data_model, path) is _MISSING:
            issues.append(f"bound path '{path}' has no initial value in data_model")
    return issues


def build_a2ui_messages(
    surface_id: str, component_tree: dict, data_model: Optional[dict] = None
) -> list[dict]:
    """The validated three-message A2UI array for one surface."""
    if not isinstance(surface_id, str) or not surface_id.strip():
        raise A2UIValidationError(["surface_id must be a non-empty string"])
    if not _has(component_tree, "component"):
        raise A2UIValidationError(["component_tree must be one component object with a 'component' name"])
    data_model = data_model or {}
    components = flatten(component_tree)
    issues = validate(components, data_model)
    if issues:
        raise A2UIValidationError(issues)
    return [
        {"version": VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID}},
        {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
        {"version": VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": data_model}},
    ]


def build_a2ui_block(surface_id: str, component_tree: dict, data_model: Optional[dict] = None) -> str:
    """The validated surface as an ``atx-a2ui`` fenced block for a chat message."""
    messages = build_a2ui_messages(surface_id, component_tree, data_model)
    return f"```{BLOCK_TAG}\n{json.dumps(messages, ensure_ascii=False)}\n```"


@tool
def render_a2ui_surface(surface_id: str, component_tree: dict, data_model: Optional[dict] = None) -> str:
    """Validate an A2UI surface for AWS Transform chat and return the block to put in your reply.

    Args:
        surface_id: Stable kebab-case ID, e.g. "migration-preferences" or "display-servers".
        component_tree: One nested root component, e.g. {"component": "SpaceBetween", "children": [...]}.
            Nest child components directly in children, footer, actions or a Header description,
            and in tabs/steps items as "content". IDs are optional.
        data_model: Initial data model, e.g. {"form": {"region": ""}}. Every bound path needs a value.

    Returns:
        The fenced atx-a2ui block. Copy it unchanged into your reply. On failure, "Error:" and every
        problem to fix before calling again.
    """
    try:
        return build_a2ui_block(surface_id, component_tree, data_model)
    except A2UIValidationError as e:
        return "Error: fix all of these, then call again:\n" + "\n".join(f"- {i}" for i in e.issues)


@tool
def suggest_replies(suggestions: list[str]) -> str:
    """Attach one-click reply suggestions to your next chat message.

    Args:
        suggestions: One to five short, self-contained instructions, e.g. ["Run the full assessment"].
            Clicking one sends its text as the customer's next message.

    Returns:
        "OK", or "Error:" and what to fix.
    """
    if not 1 <= len(suggestions) <= 5 or not all(isinstance(s, str) and s.strip() for s in suggestions):
        return "Error: pass one to five non-empty strings"
    add_suggestions([s.strip() for s in suggestions])
    return "OK"
