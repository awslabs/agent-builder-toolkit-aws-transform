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


class A2UIValidationError(ValueError):
    """A surface the web app would not render. ``issues`` lists every problem found."""

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


@cache
def load_catalog() -> dict:
    """The ``atx-hitl/v1`` catalog: components, their props, platform actions, functions."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _is_component(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("component"), str)


def flatten(component_tree: dict) -> list[dict]:
    """Turn one nested component tree into the flat A2UI adjacency list.

    Child components nested in any prop, or in ``tabs``/``steps`` items as ``content``,
    become ID references. The root gets ID ``root`` and comes first; other components
    keep their ``id`` or get a generated one.
    """
    flat: list[dict] = []
    counter = itertools.count(1)

    def visit(node: dict, cid: str) -> str:
        out: dict = {"id": cid}
        flat.append(out)
        for key, value in node.items():
            if key != "id":
                out[key] = convert(key, value)
        return cid

    def child(node: dict) -> str:
        return visit(node, node.get("id") or f"{node['component'].lower()}-{next(counter)}")

    def convert(key: str, value: Any) -> Any:
        if _is_component(value):
            return [child(value)]
        if not isinstance(value, list):
            return value
        items = []
        for item in value:
            if _is_component(item):
                item = child(item)
            elif key in _ITEM_CONTENT_PROPS and isinstance(item, dict) and _is_component(item.get("content")):
                content = item["content"]
                item = {k: v for k, v in item.items() if k != "content"}
                item["contentId"] = child(content)
            items.append(item)
        return items

    visit(component_tree, "root")
    return flat


def _bound_paths(value: Any) -> set[str]:
    """Absolute data-model paths bound anywhere in ``value``."""
    if isinstance(value, list):
        return set().union(*map(_bound_paths, value)) if value else set()
    if not isinstance(value, dict):
        return set()
    found = set().union(*map(_bound_paths, value.values())) if value else set()
    path = value.get("path")
    if isinstance(path, str) and path.startswith("/"):
        found.add(path)
    return found


def _resolves(model: Any, path: str) -> bool:
    for part in path.strip("/").split("/"):
        if isinstance(model, dict) and part in model:
            model = model[part]
        elif isinstance(model, list) and part.isdigit() and int(part) < len(model):
            model = model[int(part)]
        else:
            return False
    return True


def _item_issues(where: str, item_spec: dict, items: list) -> list[str]:
    """Unknown and missing keys in the items of an array prop, e.g. Table columnDefinitions.

    The web app reads only the keys the catalog names, so a column with `key` instead of
    `field` renders as an empty column. A key is optional when its catalog entry ends in "?"
    or says "optional", "default" or "(for ...)"; every other key is required.
    """
    allowed, required = set(), set()
    for k, v in item_spec.items():
        name = k.rstrip("?")
        allowed.add(name)
        text = json.dumps(v).lower()
        optional = k.endswith("?") or any(w in text for w in ("optional", "default", "(for "))
        if (isinstance(v, dict) and v.get("required")) or (not isinstance(v, dict) and not optional):
            required.add(name)
    issues = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        issues += [f"{where}[{i}] has no key '{k}' (allowed: {', '.join(sorted(allowed))})" for k in sorted(item.keys() - allowed)]
        issues += [f"{where}[{i}] is missing '{k}'" for k in sorted(required - item.keys())]
    return issues


def validate(components: list[dict], data_model: dict) -> list[str]:
    """Every catalog and protocol problem in a flat surface, or [] when it will render."""
    catalog = load_catalog()
    specs, universal = catalog["components"], set(catalog.get("universalProps", {}))
    issues = []
    ids = [c.get("id") for c in components]
    if not ids or ids[0] != "root":
        issues.append("the first component must have id 'root'")
    issues += [f"duplicate component id '{d}'" for d in sorted({i for i in ids if ids.count(i) > 1})]
    known = set(ids)

    for c in components:
        cid, name = c.get("id"), c.get("component")
        spec = specs.get(name)
        if spec is None:
            issues.append(f"{cid}: unknown component '{name}'; see references/catalog.json")
            continue
        props = spec.get("props", {})
        for prop in sorted(c.keys() - props.keys() - universal - {"id", "component"}):
            issues.append(f"{cid}: {name} has no prop '{prop}' (allowed: {', '.join(sorted(props))})")
        for prop, prop_spec in props.items():
            if prop_spec.get("required") and prop not in c:
                issues.append(f"{cid}: {name} is missing required prop '{prop}'")
            if "ChildList" in str(prop_spec.get("type")) and isinstance(c.get(prop), list):
                refs = [r for r in c[prop] if isinstance(r, str)]
                issues += [f"{cid}: '{prop}' references unknown component '{r}'" for r in refs if r not in known]
        for prop, prop_spec in props.items():
            if isinstance(prop_spec.get("items"), dict) and isinstance(c.get(prop), list):
                issues += _item_issues(f"{cid}: {name}.{prop}", prop_spec["items"], c[prop])
        for prop in sorted(_ITEM_CONTENT_PROPS & c.keys()):
            items = c[prop] if isinstance(c[prop], list) else []
            refs = [i.get("contentId") for i in items if isinstance(i, dict) and "contentId" in i]
            issues += [f"{cid}: '{prop}' references unknown component '{r}'" for r in refs if r not in known]

    if "\u00a0" in json.dumps(components, ensure_ascii=False):
        issues.append("replace non-breaking spaces (U+00A0) with ordinary spaces")
    for path in sorted(_bound_paths(components)):
        # ponytail: "__" segments are renderer-owned state (e.g. /__showValidation), not agent data.
        if not any(p.startswith("__") for p in path.split("/")) and not _resolves(data_model, path):
            issues.append(f"bound path '{path}' has no initial value in data_model")
    return issues


def build_a2ui_messages(
    surface_id: str, component_tree: dict, data_model: Optional[dict] = None
) -> list[dict]:
    """The validated three-message A2UI array for one surface."""
    if not isinstance(surface_id, str) or not surface_id.strip():
        raise A2UIValidationError(["surface_id must be a non-empty string"])
    if not _is_component(component_tree):
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
            Nest child components directly in children, footer, actions or description, and in
            tabs/steps items as "content". IDs are optional.
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
