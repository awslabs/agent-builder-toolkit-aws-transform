# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the A2UI surface builder and its agent tools."""

import json
import logging
import textwrap
from types import SimpleNamespace

import pytest

from agent_builder_sdk.constants import GUARDRAIL_STOP_REASONS
from agent_builder_sdk.ui_chat import a2ui
from agent_builder_sdk.ui_chat.a2ui import (
    SURFACES_STATE_KEY,
    A2UIValidationError,
    add_missing_surfaces,
    build_a2ui_block,
    build_a2ui_messages,
    flatten,
    forget_surfaces_in,
    render_a2ui_surface,
    suggest_replies,
    take_surfaces,
)

FORM = {
    "component": "SpaceBetween",
    "children": [
        {
            "component": "FormField",
            "label": "Target region",
            "children": [{"component": "Input", "value": {"path": "/form/region"}}],
        },
        {"component": "SubmitButton", "children": "Submit"},
    ],
}
BOX = {"component": "Box", "children": "x"}
COLS = [{"id": "name", "header": "Name", "field": "name"}]
ROWS = [{"name": "payments-api"}]
XY = [{"x": 1, "y": 12}]
INVENTORY = {"inventory": {"apps": ROWS}}


def _table(items, **props):
    return {"component": "Table", "columnDefinitions": COLS, "items": items, **props}


def _cards(items, **card):
    return {"component": "Cards", "items": items, "cardDefinition": card}


def _issues(tree, data_model=None):
    with pytest.raises(A2UIValidationError) as e:
        build_a2ui_messages("s", tree, data_model)
    return e.value.issues


def test_catalog_ships_with_the_skill():
    catalog = a2ui.load_catalog()
    assert catalog["catalogId"] == a2ui.CATALOG_ID
    assert {"Table", "FormField", "SubmitButton", "MermaidDiagram"} <= catalog["components"].keys()


def test_flatten_puts_root_first_and_turns_nesting_into_id_references():
    flat = flatten(FORM)
    assert flat[0]["id"] == "root"
    by_id = {c["id"]: c for c in flat}
    assert len(by_id) == 4
    field_id, submit_id = flat[0]["children"]
    assert by_id[field_id]["component"] == "FormField"
    assert by_id[by_id[field_id]["children"][0]]["component"] == "Input"
    assert by_id[submit_id]["children"] == "Submit"  # text children stay text


def test_flatten_moves_tab_content_to_content_id_and_keeps_explicit_ids():
    tree = {
        "component": "Tabs",
        "tabs": [{"id": "t1", "label": "One", "content": {"id": "body", "component": "Box", "children": "x"}}],
    }
    root, body = flatten(tree)
    assert root["tabs"] == [{"id": "t1", "label": "One", "contentId": "body"}]
    assert body["id"] == "body"


def test_flatten_gives_a_tab_or_step_without_id_the_id_of_its_content():
    root, body = flatten({"component": "MultiStepForm", "steps": [{"content": BOX}]})
    assert root["steps"] == [{"contentId": body["id"], "id": body["id"]}]
    assert build_a2ui_messages("s", {"component": "Tabs", "tabs": [{"label": "One", "content": BOX}]})


def test_flatten_keeps_inline_rows_as_data():
    # A row field named `component` is not a child component, and one named `path` is not a binding.
    rows = [{"component": "payments-api", "path": "/src/app.py"}]
    cols = [{"id": "component", "header": "Component", "field": "component"}]
    for items in (rows, tuple(rows)):
        tree = {"component": "SpaceBetween", "children": [_table(items, columnDefinitions=cols)]}
        root, table = build_a2ui_messages("s", tree)[1]["updateComponents"]["components"]
        assert root["children"] == [table["id"]] and table["items"] == items


def test_flatten_takes_a_tuple_as_a_list():
    tabs = {"component": "Tabs", "tabs": ({"label": "One", "content": BOX},)}
    root, box, tabbed, body = flatten({"component": "SpaceBetween", "children": (BOX, tabs)})
    assert root["children"] == [box["id"], tabbed["id"]]
    assert tabbed["tabs"] == [{"label": "One", "contentId": body["id"], "id": body["id"]}]


def test_generated_ids_skip_explicit_ids():
    container = {"component": "Container", "children": [BOX]}
    for kids in ([container, {**container, "id": "container-1"}], [{**container, "id": "container-2"}, container]):
        tree = {"component": "SpaceBetween", "children": kids}
        ids = [c["id"] for c in flatten(tree)]
        assert len(set(ids)) == len(ids)
        assert build_a2ui_messages("s", tree)


def test_block_is_the_three_message_array_in_an_atx_a2ui_fence():
    block = build_a2ui_block("migration-preferences", FORM, {"form": {"region": ""}})
    assert block.startswith("```atx-a2ui\n") and block.endswith("\n```")
    create, update, data = json.loads(block[len("```atx-a2ui\n") : -len("\n```")])
    assert create == {"version": "v0.9", "createSurface": {"surfaceId": "migration-preferences", "catalogId": "atx-hitl/v1"}}
    assert update["updateComponents"]["components"][0]["id"] == "root"
    assert data["updateDataModel"] == {"surfaceId": "migration-preferences", "path": "/", "value": {"form": {"region": ""}}}


def test_reports_every_problem_at_once():
    tree = {
        "component": "SpaceBetween",
        "children": [
            {"component": "Blink"},
            {"component": "MermaidDiagram", "diagram": "graph TD"},
            {"id": "dup", "component": "Box", "children": "a"},
            {"id": "dup", "component": "Box", "children": "b"},
            {"component": "Input", "value": {"path": "/form/missing"}},
        ],
    }
    issues = "\n".join(_issues(tree))
    assert "unknown component 'Blink'" in issues
    assert "MermaidDiagram has no prop 'diagram'" in issues
    assert "MermaidDiagram is missing required prop 'content'" in issues
    assert "duplicate component id 'dup'" in issues
    assert "bound path '/form/missing' has no initial value" in issues


def test_unknown_child_reference_and_non_breaking_space():
    issues = "\n".join(_issues({"component": "SpaceBetween", "children": ["nowhere", {"component": "Box", "children": "a\u00a0b"}]}))
    assert "references unknown component 'nowhere'" in issues
    assert "non-breaking spaces" in issues


def test_renderer_owned_paths_need_no_initial_value():
    tree = {"component": "Input", "value": {"path": "/form/name"}, "visible": {"path": "/form/__shown"}}
    build_a2ui_messages("s", tree, {"form": {"name": ""}})


@pytest.mark.parametrize("path", [
    "/inventory/apps/1/name", "/inventory/apps/name", "/inventory/apps/0/name/0", "/inventory/apps/0/name/api",
    "/inventory/apps/\u00b2", "/inventory/apps/\u0660",
])
def test_a_path_that_does_not_resolve_has_no_initial_value(path):
    # An index goes into an array only and not past its end; a key goes into an object only.
    # An index is ASCII digits: not "\u00b2" (superscript two) or "\u0660" (Arabic-Indic zero), which str.isdigit() takes.
    assert _issues({"component": "Box", "children": {"path": path}}, INVENTORY) == [f"bound path '{path}' has no initial value in data_model"]


def test_table_columns_must_use_the_catalog_keys():
    # Columns with `key` in place of `field` render as empty rows.
    rows = [{"name": "payments-api"}]
    bad = {"component": "Table", "items": rows, "columnDefinitions": [{"id": "name", "header": "Name", "key": "name"}]}
    assert _issues(bad) == [
        "root: Table.columnDefinitions[0] has no key 'key' (allowed: field, header, id, sortType, sortable)",
        "root: Table.columnDefinitions[0] is missing 'field'",
    ]
    good = {"component": "Table", "items": rows, "columnDefinitions": [{"id": "name", "header": "Name", "field": "name"}]}
    assert build_a2ui_messages("s", good)


def test_table_items_must_be_an_array_or_a_binding():
    # Items given as the text "{{inventory.apps}}" render "No data".
    cols = [{"id": "name", "header": "Name", "field": "name"}]
    bad = {"component": "Table", "items": "{{inventory.apps}}", "columnDefinitions": cols}
    assert _issues(bad) == ['root: Table.items is a string; give an array or a binding like {"path": "/data/items"}']
    good = {"component": "Table", "items": {"path": "/inventory/apps"}, "columnDefinitions": cols}
    assert build_a2ui_messages("s", good, {"inventory": {"apps": [{"name": "payments-api"}]}})


def test_optional_item_keys_may_be_left_out():
    tree = {"component": "SpaceBetween", "children": [
        {"component": "Autosuggest", "value": {"path": "/q"}, "options": [{"value": "a"}]},
        {"component": "BarChart", "series": [{"title": "Lines", "data": [{"x": "a", "y": 1}]}]},
        {"component": "LineChart", "series": [{"title": "p50", "type": "line", "data": XY}, {"title": "SLA", "y": 50}]},
        {"component": "AreaChart", "series": [{"title": "EC2", "type": "area", "data": XY}, {"title": "Cap", "y": 50}]},
        {"component": "KeyValuePairs", "items": [{"label": "Owner", "value": "team-a"}]},
    ]}
    assert build_a2ui_messages("s", tree, {"q": ""})


@pytest.mark.parametrize(
    ("tree", "data_model"),
    [
        # Text props take text, a binding or a call; component-list props take components.
        ({"component": "Alert", "children": "3 failed", "action": {"component": "Button", "children": "Retry"}}, None),
        ({"component": "Header", "children": "Apps", "counter": 3, "description": [BOX]}, None),
        ({"component": "Box", "children": {"call": "formatNumber", "args": {"value": {"path": "/data/n"}}}}, {"data": {"n": 3}}),
        # A string, boolean or number prop takes text, a boolean or a number; a Dynamic one also takes a binding or a call.
        ({"component": "Button", "children": "Download", "iconName": "download", "fullWidth": True,
          "disabled": {"path": "/form/busy"}, "loading": {"call": "not", "args": {"value": {"path": "/form/busy"}}}},
         {"form": {"busy": False}}),
        ({"component": "ProgressBar", "value": {"path": "/data/percent"}}, {"data": {"percent": 40}}),
        ({"component": "ProgressBar", "value": 40}, None),
        ({"component": "ProgressBar", "value": {"call": "formatNumber", "args": {"value": {"path": "/data/percent"}}}},
         {"data": {"percent": 40}}),
        (_table(ROWS, visible=False, pageSize=25), None),
        # A prop with catalog values takes a binding or a call too.
        ({"component": "StatusIndicator", "type": {"path": "/data/status"}, "children": "Ready"}, {"data": {"status": "success"}}),
        ({"component": "StatusIndicator", "type": {"call": "formatString", "args": {"value": "${/data/status}"}}, "children": "Ready"},
         {"data": {"status": "success"}}),
        # An `id` that is not a string gives way to a generated ID.
        ({"component": "SpaceBetween", "children": [{"id": 7, **BOX}]}, None),
        # Array props: a tuple is an array, a bound array may start as null, a single selection is one ID.
        (_table(tuple(ROWS)), None),
        (_table({"path": "/inventory/apps"}), {"inventory": {"apps": None}}),
        (_table(ROWS, selectionType="single", selectedItems={"path": "/form/app"}), {"form": {"app": "payments-api"}}),
        (_table(ROWS, selectionType="multi", selectedItems=["payments-api"]), None),
        # An array prop with no catalog item keys takes plain values.
        (_table(ROWS, filteringFields=["name"]), None),
        # An item key with a catalog type takes the forms of a prop of that type: text, a number, a binding, a call. Null is no value.
        ({"component": "KeyValuePairs", "items": [
            {"label": "Status", "value": {"path": "/data/status"}, "statusType": {"path": "/data/statusType"}},
            {"label": "Servers", "value": 3, "statusType": "success"},
            {"label": "Cost", "value": {"call": "formatCurrency", "args": {"value": 1200}}, "statusType": None}]},
         {"data": {"status": "Ready", "statusType": "success"}}),
        # Rows from the data model, and their nested lists such as chart points, may have keys that the catalog does not name.
        ({"component": "Select", "options": {"path": "/regions"}}, {"regions": [{"value": "us-east-1", "label": "N. Virginia", "azs": 6}]}),
        ({"component": "LineChart", "series": {"path": "/series"}}, {"series": [{"title": "p50", "unit": "ms", "data": [{"x": 1, "y": 12, "note": "n"}]}]}),
        # A bound path may go through an array index.
        ({"component": "Box", "children": {"path": "/inventory/apps/0/name"}}, INVENTORY),
        # An action context maps free names to values, so a name may be "path".
        ({"component": "Button", "children": "View", "action": {"event": {"name": "view", "context": {"path": "/src/app.py"}}}}, None),
        # Valid: a table with no rows, a column that only some rows have or that is empty in this data, a card with a title only.
        (_table([]), None),
        (_table([{"error": "timeout"}, *ROWS]), None),
        (_table(ROWS, columnDefinitions=[*COLS, {"id": "error", "header": "Error", "field": "error"}]), None),
        (_cards({"path": "/inventory/apps"}, header="name"), INVENTORY),
    ],
)
def test_accepts_the_forms_the_catalog_and_the_docs_give(tree, data_model):
    assert build_a2ui_messages("s", tree, data_model)


@pytest.mark.parametrize("name", [5, ["Box"], {"a": 1}])
def test_a_component_name_that_is_not_a_string_is_reported_not_raised(name):
    # flatten() and validate() are public, so a caller can hand them a tree build_a2ui_messages refuses.
    tree = {"component": name, "children": "x"}
    with pytest.raises(A2UIValidationError):
        build_a2ui_block("s", tree)
    assert flatten(tree) == [{"id": "root", **tree}]
    assert a2ui.validate(flatten(tree), {}) == [f"root: unknown component '{name}'; see references/catalog.json"]


def test_validate_reports_duplicate_ids_of_any_type():
    # A flat list that flatten() did not make can have an `id` that is not a string, or not hashable.
    flat = [{"id": "root", "component": "SpaceBetween", "children": ["a"]}, *[{"id": i, **BOX} for i in (7, 7, "a", "a", ["b"], ["b"])]]
    assert a2ui.validate(flat, {}) == ["duplicate component id '7'", "duplicate component id '['b']'", "duplicate component id 'a'"]


def test_relative_paths_are_valid_under_a_template():
    # A path with no leading "/" is relative to the current array item, so it is not looked up from the root.
    flat = [
        {"id": "root", "component": "SpaceBetween", "children": {"componentId": "item", "path": "/apps"}},
        {"id": "item", "component": "TokenGroup", "items": {"path": "tags"}},
    ]
    assert a2ui.validate(flat, {"apps": [{"tags": [{"label": "java"}]}], "tags": "none"}) == []


@pytest.mark.parametrize(
    ("tree", "data_model", "issues"),
    [
        # A text prop takes no component, list or other object. A component-list prop takes no text,
        # and no object but a {"componentId", "path"} template that names a component of the surface.
        ({"component": "Container", "header": {"component": "Header", "children": "Apps"}, "children": [BOX]}, None,
         ['root: Container.header is a component or a list; give text or a binding like {"path": "/data/title"}']),
        ({"component": "Header", "children": {"literalString": "Apps"}}, None,
         ['root: Header.children is an object; give text or a binding like {"path": "/data/title"}']),
        ({"component": "Container", "children": "3 apps found"}, None,
         ['root: Container.children is a string; give a list of components like [{"component": "TextContent", "children": "..."}]']),
        ({"component": "SpaceBetween", "children": {"path": "/inventory/apps"}}, INVENTORY,
         ['root: SpaceBetween.children is an object; give a list of components like [{"component": "TextContent", "children": "..."}]']),
        ({"component": "SpaceBetween", "children": {"componentId": "row"}}, None,
         ['root: SpaceBetween.children is an object; give a list of components like [{"component": "TextContent", "children": "..."}]']),
        ({"component": "SpaceBetween", "children": {"componentId": "row", "path": "/inventory/apps"}}, INVENTORY,
         ["root: 'children' references unknown component 'row'"]),
        ({"component": "SpaceBetween", "children": [{"type": "Box", "children": "x"}]}, None,
         ['root: SpaceBetween.children takes components: each entry is an object with a "component" name']),
        # A tab or step `content` that is not one component gets one message. A `contentId` is the ID of a component of the surface.
        ({"component": "Tabs", "tabs": [{"label": "One", "content": [BOX, BOX]}]}, None,
         ['root: Tabs.tabs[0].content must be one component, e.g. {"component": "SpaceBetween", "children": [...]}']),
        ({"component": "Tabs", "tabs": [{"id": "one", "label": "One", "contentId": BOX}]}, None,
         ["root: Tabs.tabs[0].contentId must be a string. Catalog: string (component ID)"]),
        ({"component": "Tabs", "tabs": [{"id": "one", "label": "One"}, {"id": "two", "label": "Two", "contentId": "nowhere"}]}, None,
         ["root: Tabs.tabs[0] is missing 'contentId'", "root: 'tabs' references unknown component 'nowhere'"]),
        # A null `contentId` names no component. One that is a list, and a step that is not an object, get the item message only.
        ({"component": "MultiStepForm", "steps": [{"id": "one", "contentId": None}, {"id": "two", "contentId": ["body"]}, 5]}, None,
         ["root: MultiStepForm.steps[1].contentId must be a string. Catalog: string...",
          "root: MultiStepForm.steps[2] must be an object with keys contentId, id",
          "root: 'steps' references unknown component 'None'"]),
        # Array props take an array or, where the catalog offers it, a binding to an array.
        (_table({"binding": "/inventory/apps"}), INVENTORY,
         ['root: Table.items is an object; give an array or a binding like {"path": "/data/items"}']),
        ({"component": "Tabs", "tabs": 5}, None, ["root: Tabs.tabs is 5; give an array"]),
        (_table(None), None, ["root: Table is missing required prop 'items'"]),
        (_table({"path": "/inventory"}), INVENTORY,
         ["root: Table.items is bound to '/inventory', which is not an array in data_model; bind an array ([] when empty)"]),
        ({"component": "FileUpload", "value": {"path": "/inventory"}}, INVENTORY,
         ["root: FileUpload.value is bound to '/inventory', which is not an array in data_model; bind an array ([] when empty)"]),
        ({"component": "KeyValuePairs", "items": {"Region": "us-east-1"}}, None, ["root: KeyValuePairs.items is an object; give an array"]),
        ({"component": "Select", "options": "{{regions}}"}, None,
         ['root: Select.options is a string; give an array or a binding like {"path": "/data/items"}']),
        ({"component": "FileUpload", "value": "files"}, None,
         ['root: FileUpload.value is a string; give a binding like {"path": "/data/items"}']),
        # Items are objects with the catalog keys. Data rows and chart points get the first faulty item only.
        ({"component": "Select", "options": ["us-east-1", "us-west-2"]}, None,
         ["root: Select.options[0] must be an object with keys label, value", "root: Select.options[1] must be an object with keys label, value"]),
        ({"component": "KeyValuePairs", "items": [{"label": "Owner"}]}, None, ["root: KeyValuePairs.items[0] is missing 'value'"]),
        ({"component": "MixedLineBarChart", "series": [{"title": "Revenue", "data": XY}]}, None,
         ["root: MixedLineBarChart.series[0] is missing 'type'"]),
        ({"component": "PieChart", "data": {"path": "/slices"}}, {"slices": [{"name": "Java", "value": 1}, {"name": ".NET", "value": 2}]},
         ["root: PieChart.data[0] is missing 'title'"]),
        (_table({"path": "/rows"}), {"rows": [["payments-api"], ["ledger-svc"]]},
         ["root: Table.items rows must be objects with named fields. Catalog: Array of row objects..."]),
        ({"component": "BarChart", "series": [{"title": "Lines", "data": [["Java", 120000], ["Go", 9000]]}]}, None,
         ["root: BarChart.series[0].data[0] must be an object with keys x, y"]),
        # A key that the catalog types as a string takes no list, and a tuple from a Python caller is a list.
        (_table(ROWS, columnDefinitions=[{"id": "name", "header": ["Name"], "field": ("name",)}]), None,
         ["root: Table.columnDefinitions[0].header must be a string. Catalog: string",
          "root: Table.columnDefinitions[0].field must be a string. Catalog: string"]),
        # An item key with a catalog type takes the forms and the values of a prop of that type.
        ({"component": "KeyValuePairs", "items": [
            {"label": "Status", "value": {"component": "StatusIndicator", "type": "success", "children": "Ready"}},
            {"label": ["Owner"], "value": "team-a", "statusType": "ok"}]}, None,
         ['root: KeyValuePairs.items[0].value is an object; give text or a binding like {"path": "/data/title"}',
          "root: KeyValuePairs.items[1].label is a component or a list; give text",
          'root: KeyValuePairs.items[1].statusType must be one of "error", "warning", ...']),
        # A key that is not a string (Python callers only) is reported like any other unknown key.
        ({"component": "Select", "options": [{"value": "a", "label": "A", 1: "x", "zz": "y"}], 5: "x", "zzz": "y"}, None,
         ["root: Select has no prop '5' (allowed: ...", "root: Select has no prop 'zzz' (allowed: ...",
          "root: Select.options[0] has no key '1' (allowed: label, value)",
          "root: Select.options[0] has no key 'zz' (allowed: label, value)"]),
        # A bound path is an absolute JSON Pointer.
        (_table({"path": "inventory.apps"}), INVENTORY,
         ["bound path 'inventory.apps' must start with '/' and use '/' between keys, e.g. '/data/items'"]),
        # Cards.cardDefinition has the catalog keys, and its field names are row keys.
        (_cards(ROWS, title="name", sections=[{"id": "n", "content": "name"}]), None,
         ["root: Cards.cardDefinition has no key 'title' (allowed: header, sections)",
          "root: Cards.cardDefinition is missing 'header'",
          "root: Cards.cardDefinition.sections[0] has no key 'content' (allowed: field, header)",
          "root: Cards.cardDefinition.sections[0] has no key 'id' (allowed: field, header)",
          "root: Cards.cardDefinition.sections[0] is missing 'field'"]),
        (_cards(ROWS, header={"field": "name"}), None,
         ["root: Cards.cardDefinition.header must be a string. Catalog: string (field name for card title)"]),
        (_cards(ROWS, header="name", sections="name"), None,
         ["root: Cards.cardDefinition.sections must be an array of objects with keys field, header"]),
        (_cards([{"name": "web-01", "os": "linux"}], header="Name", sections=[{"field": "os"}]), None,
         ["root: Cards field 'Name' is not a key of any row (row keys: name, os); did you mean 'name'?"]),
        (_cards([{"name": "web-01", "os_name": "linux", "cpuCount": 4}], header="name", sections=[{"field": "osName"}, {"field": "cpu_count"}]), None,
         ["root: Cards field 'osName' is not a key of any row (row keys: cpuCount, name, os_name); did you mean 'os_name'?",
          "root: Cards field 'cpu_count' is not a key of any row (row keys: cpuCount, name, os_name); did you mean 'cpuCount'?"]),
        (_table({"path": "/inventory/apps"}, columnDefinitions=[{"id": "app", "header": "App", "field": "app"}]), INVENTORY,
         ["root: Table field 'app' is not a key of any row (row keys: name)"]),
        # Enum, boolean and number props take the catalog values, not look-alike text or an event object.
        ({"component": "Alert", "type": "danger", "children": "x"}, None,
         ['root: Alert.type must be one of "success", "error", "warning", "info"']),
        ({"component": "SubmitButton", "action": {"event": {"name": "atx:submit"}}}, None,
         ['root: SubmitButton.action must be one of "atx:submit", ...']),
        (_table(ROWS, visible="no", loading="false", pageSize="25"), None,
         ["root: Table.visible is a string; give true or false, without quotes",
          "root: Table.loading is a string; give true or false, without quotes",
          "root: Table.pageSize is a string; give a number, without quotes"]),
        ({"component": "ProgressBar", "value": "40"}, None, ["root: ProgressBar.value is a string; give a number, without quotes"]),
        # Such a prop takes no component, list or other object: flatten() turns a nested component into an ID list.
        # String, boolean and number props each have their own rule, so each gets a list and an object.
        ({"component": "ExpandableSection", "headerText": "Details", "children": [BOX],
          "headerDescription": {"binding": "/data/d"}, "headerCounter": {"component": "Badge", "children": "3"}}, None,
         ["root: ExpandableSection.headerDescription is an object; give text",
          "root: ExpandableSection.headerCounter is a component or a list; give text"]),
        (_table(ROWS, loading=[True], filtering={"literal": True}, pageSize={"binding": "/n"}), None,
         ["root: Table.loading is a component or a list; give true or false, without quotes",
          "root: Table.filtering is an object; give true or false, without quotes",
          "root: Table.pageSize is an object; give a number, without quotes"]),
        ({"component": "ProgressBar", "value": [40]}, None,
         ["root: ProgressBar.value is a component or a list; give a number, without quotes"]),
        # A call names a catalog function. An unknown name is reported once.
        ({"component": "Box", "children": {"call": "concat", "args": {}}, "visible": {"call": "concat", "args": {}}}, None,
         ["unknown function 'concat' (catalog functions: add, and, ..."]),
    ],
)
def test_rejects_the_forms_the_catalog_does_not_give(tree, data_model, issues):
    # Messages are compared in full. Only an expected message that ends in "..." gives the start of a longer one.
    found = [f[: len(e) - 3] + "..." if e.endswith("...") else f for f, e in zip(_issues(tree, data_model), issues, strict=True)]
    assert found == issues


def test_rejects_a_bad_surface_id_or_root():
    with pytest.raises(A2UIValidationError):
        build_a2ui_messages("", FORM)
    with pytest.raises(A2UIValidationError):
        build_a2ui_messages("s", [FORM])


def test_render_tool_returns_block_or_error_list():
    assert render_a2ui_surface(surface_id="s", component_tree=FORM, data_model={"form": {"region": ""}}).startswith("```atx-a2ui")
    out = render_a2ui_surface(surface_id="s", component_tree={"component": "Blink"})
    assert out.startswith("Error:") and "unknown component 'Blink'" in out


def test_suggest_replies_attaches_suggestions(monkeypatch):
    got = []
    monkeypatch.setattr(a2ui, "add_suggestions", got.append)
    assert suggest_replies(suggestions=[" Run the full assessment "]) == "OK"
    assert got == [["Run the full assessment"]]
    assert suggest_replies(suggestions=[]).startswith("Error:")
    assert suggest_replies(suggestions=["a"] * 6).startswith("Error:")


TABLE = _table({"path": "/data/apps"})


def _apps(*names):
    return {"data": {"apps": [{"name": name} for name in names]}}


BLOCK = build_a2ui_block("inventory", TABLE, _apps("payments-api"))
BODY = BLOCK.split("\n")[1]


def _render(state, surface_id="inventory", tree=TABLE, data_model=None):
    """Call the tool with the request state of a turn, as the agent loop does."""
    context = SimpleNamespace(invocation_state={"request_state": state})
    data_model = _apps("payments-api") if data_model is None else data_model
    return render_a2ui_surface(surface_id=surface_id, component_tree=tree, data_model=data_model, tool_context=context)


def _result(surfaces, stop_reason="end_turn"):
    """The part of an agent result that the reply sites read."""
    return SimpleNamespace(state={SURFACES_STATE_KEY: dict(surfaces)}, stop_reason=stop_reason)


def test_render_tool_records_a_valid_surface_for_the_turn():
    state = {}
    assert _render(state) == BLOCK
    assert state == {SURFACES_STATE_KEY: {"inventory": BLOCK}}


def test_render_tool_records_nothing_for_a_validation_error():
    state = {}
    assert _render(state, tree={"component": "Blink"}).startswith("Error:")
    assert state == {}
    # A failed render of a surface that has a valid one keeps the valid block.
    _render(state)
    assert _render(state, tree={"component": "Blink"}).startswith("Error:")
    assert state == {SURFACES_STATE_KEY: {"inventory": BLOCK}}


def test_render_tool_keeps_the_last_valid_render_of_a_surface_and_moves_it_last():
    state = {}
    _render(state, "inventory")
    _render(state, "Summary", BOX, {})
    latest = _render(state, "inventory", data_model=_apps("payments-api", "ledger-svc"))
    assert list(state[SURFACES_STATE_KEY]) == ["Summary", "inventory"]
    assert state[SURFACES_STATE_KEY]["inventory"] == latest != BLOCK


def test_render_tool_without_a_turn_returns_the_block():
    assert render_a2ui_surface(surface_id="inventory", component_tree=TABLE, data_model=_apps("payments-api")) == BLOCK


def test_render_tool_does_not_show_the_model_its_context_parameter():
    shown = set(render_a2ui_surface.tool_spec["inputSchema"]["json"]["properties"])
    assert shown == {"surface_id", "component_tree", "data_model"}


@pytest.mark.parametrize("tool", [render_a2ui_surface, suggest_replies])
def test_tools_tell_the_model_to_call_tools_before_it_writes_the_reply(tool):
    description = " ".join(tool.tool_spec["description"].split())
    assert "a message that also calls a tool is not part of the reply" in description


@pytest.mark.parametrize(
    "skill, rule",
    [
        ("a2ui-rendering", "Text in a message that also calls a tool is not part of the reply."),
        ("a2ui-rendering", "Write the reply last, in a message with no tool call, with the block in it"),
        ("a2ui-rendering", "A surface that rendered without an error earlier in the turn stays in the reply"),
        ("a2ui-rendering", "To change a surface in the same turn, render it again with the same ID."),
        ("a2ui-ux-patterns", "`suggest_replies`, before you write the response."),
        ("a2ui-ux-patterns", "in the same final message as the block."),
        ("user-chat", "put everything the customer must see, a rendered surface included, in the last message"),
    ],
)
def test_skills_tell_the_model_to_put_the_surface_in_its_last_message(skill, rule):
    text = (a2ui.CATALOG_PATH.parents[2] / skill / "SKILL.md").read_text(encoding="utf-8")
    assert rule in " ".join(text.split())


def test_render_tool_tells_the_model_to_reuse_the_surface_id_for_a_change():
    described = render_a2ui_surface.tool_spec["inputSchema"]["json"]["properties"]["surface_id"]["description"]
    assert "render it again with the same ID" in " ".join(described.split())


def test_missing_block_goes_before_the_text_after_a_blank_line():
    assert add_missing_surfaces("Closing sentence.", _result({"inventory": BLOCK})) == f"{BLOCK}\n\nClosing sentence."


@pytest.mark.parametrize("copy", [BLOCK, textwrap.indent(BLOCK, "    ")], ids=["exact", "indented"])
def test_reply_that_holds_the_rendered_block_is_left_as_it_is(copy):
    text = f"Here is the inventory.\n\n{copy}\n\nClosing sentence."
    assert add_missing_surfaces(text, _result({"inventory": BLOCK})) == text


def _copy(change):
    """A fence with the messages of BLOCK after ``change`` edited them."""
    messages = json.loads(BODY)
    change(messages)
    return f"```atx-a2ui\n{json.dumps(messages)}\n```"


@pytest.mark.parametrize(
    "copy",
    [
        f"```atx-a2ui\n{json.dumps(json.loads(BODY), indent=2)}\n```",
        f"````atx-a2ui  \n{BODY}\n````",
        BLOCK.replace("\n", "\r\n"),
        # The model changed a row, dropped the data model message, or named a component the catalog does not have.
        build_a2ui_block("inventory", TABLE, _apps("changed-by-the-model")),
        _copy(lambda messages: messages.pop()),
        _copy(lambda messages: messages[1]["updateComponents"]["components"][0].update(component="DataTable")),
    ],
    ids=["pretty-printed", "longer-fence", "crlf", "changed-row", "no-data-model", "unknown-component"],
)
def test_fence_that_creates_the_surface_becomes_the_rendered_block_in_its_place(copy):
    text = f"Here is the inventory.\n\n{copy}\n\nClosing sentence."
    out = add_missing_surfaces(text, _result({"inventory": BLOCK}))
    assert out == f"Here is the inventory.\n\n{BLOCK}\n\nClosing sentence."


def test_fence_with_no_closing_line_counts_when_the_text_ends_with_its_content():
    text = f"Here is the inventory.\n\n``` atx-a2ui\n{BODY}"
    assert add_missing_surfaces(text, _result({"inventory": BLOCK})) == f"Here is the inventory.\n\n{BLOCK}"


def test_reply_with_windows_line_ends_keeps_its_text_around_the_block():
    text = f"Here is the inventory.\n\n{BLOCK}\n\nClosing sentence.".replace("\n", "\r\n")
    out = add_missing_surfaces(text, _result({"inventory": BLOCK}))
    assert out == f"Here is the inventory.\r\n\r\n{BLOCK}\n\r\nClosing sentence."


def test_changed_copy_in_a_list_item_keeps_its_indent():
    changed = build_a2ui_block("inventory", TABLE, _apps("changed-by-the-model"))
    text = "1. The inventory:\n\n" + textwrap.indent(changed, "    ") + "\n2. Next steps."
    out = add_missing_surfaces(text, _result({"inventory": BLOCK}))
    assert out == "1. The inventory:\n\n" + textwrap.indent(BLOCK, "    ") + "\n2. Next steps."


def test_fence_that_creates_two_surfaces_becomes_both_rendered_blocks():
    first, second = build_a2ui_block("first", BOX), build_a2ui_block("second", BOX)
    merged = json.dumps(json.loads(first.split("\n")[1]) + json.loads(second.split("\n")[1]))
    out = add_missing_surfaces(f"Intro.\n\n```atx-a2ui\n{merged}\n```", _result({"first": first, "second": second}))
    assert out == f"Intro.\n\n{first}\n\n{second}"


def test_reply_that_holds_two_surfaces_gets_neither_again():
    first, second = build_a2ui_block("first", BOX), build_a2ui_block("second", BOX)
    text = f"Intro.\n\n{first}\n\n{second}\n\nClosing sentence."
    assert add_missing_surfaces(text, _result({"first": first, "second": second})) == text


def test_unreadable_fence_does_not_hide_a_surface_in_a_later_fence():
    text = f"```atx-a2ui\n{BODY[:150]}...\n```\n\n{BLOCK}"
    assert add_missing_surfaces(text, _result({"inventory": BLOCK})) == text


@pytest.mark.parametrize(
    "copy",
    [
        f"```atx-a2ui\n{BODY[:150]}...\n```",
        f"```atx-a2ui\n{BODY}\nClosing sentence.",
        "```atx-a2ui\n" + json.dumps(json.loads(BODY)[1:]) + "\n```",
        # json.loads raises RecursionError, not ValueError, for this one.
        "```atx-a2ui\n" + "[" * 100_000 + "\n```",
        "```atx-a2ui\nnull\n```",
        '```atx-a2ui\n[1, "inventory", null]\n```',
        '```atx-a2ui\n[{"createSurface": {"surfaceId": ["inventory"]}}, {"createSurface": {}}]\n```',
    ],
    ids=[
        "cut",
        "unclosed-then-text",
        "no-create-surface",
        "nested-too-deep",
        "not-an-array",
        "items-not-objects",
        "id-not-text",
    ],
)
def test_copy_that_cannot_be_the_surface_does_not_count(copy):
    text = f"Here is the inventory.\n\n{copy}"
    assert add_missing_surfaces(text, _result({"inventory": BLOCK})) == f"{BLOCK}\n\n{text}"


@pytest.mark.parametrize(
    "text",
    [
        f"The array is {BODY}",
        f"```json\n{BODY}\n```",
        f"Here it is: ```atx-a2ui\n{BODY}\n```",
        f"```atx-a2ui\n[]\n```\n{BODY}",
        '```atx-a2ui\n[{"createSurface": {"surfaceId": "inventory-2"}}]\n```',
        f"```ATX-A2UI\n{BODY}\n```",
    ],
    ids=["no-fence", "json-fence", "mid-line-fence", "after-the-fence", "other-surface", "other-case-tag"],
)
def test_surface_id_outside_an_atx_a2ui_fence_does_not_count(text):
    assert add_missing_surfaces(text, _result({"inventory": BLOCK})) == f"{BLOCK}\n\n{text}"


def test_only_the_missing_surfaces_are_added_in_render_order():
    # The IDs are not in alphabetical order, so render order is not ID order.
    first, held, last = (build_a2ui_block(sid, BOX) for sid in ("zeta", "held", "alpha"))
    text = f"Intro.\n\n{held}"
    out = add_missing_surfaces(text, _result({"zeta": first, "held": held, "alpha": last}))
    assert out == f"{first}\n\n{last}\n\n{text}"
    assert out.count("```atx-a2ui") == 3


def test_empty_text_gives_the_blocks_alone():
    first, last = build_a2ui_block("first", BOX), build_a2ui_block("last", BOX)
    assert add_missing_surfaces("", _result({"first": first, "last": last})) == f"{first}\n\n{last}"


@pytest.mark.parametrize("stop_reason", GUARDRAIL_STOP_REASONS)
def test_refusal_gets_no_surface(stop_reason):
    result = _result({"inventory": BLOCK}, stop_reason)
    assert add_missing_surfaces("I can't help with that.", result) == "I can't help with that."
    assert SURFACES_STATE_KEY not in result.state


def test_record_is_taken_so_a_second_call_adds_nothing():
    result = _result({"inventory": BLOCK})
    add_missing_surfaces("Closing sentence.", result)
    assert SURFACES_STATE_KEY not in result.state
    assert add_missing_surfaces("Closing sentence.", result) == "Closing sentence."


@pytest.mark.parametrize(
    "result",
    [
        object(),
        SimpleNamespace(state=None),
        SimpleNamespace(state={}),
        SimpleNamespace(state={"force_stop_response": "x"}),
    ],
    ids=["no-state", "state-none", "state-empty", "other-keys"],
)
def test_result_with_no_record_leaves_the_text(result):
    assert add_missing_surfaces("Closing sentence.", result) == "Closing sentence."


def test_result_with_a_record_and_no_stop_reason_gets_the_block():
    result = SimpleNamespace(state={SURFACES_STATE_KEY: {"inventory": BLOCK}})
    assert add_missing_surfaces("Closing sentence.", result) == f"{BLOCK}\n\nClosing sentence."


def test_surface_id_with_quotes_or_non_ascii_text_is_found():
    for surface_id in ('say "hi"', "caf\u00e9-inventory"):
        block = build_a2ui_block(surface_id, BOX)
        escaped = "```atx-a2ui\n" + json.dumps(json.loads(block.split("\n")[1])) + "\n```"  # \uXXXX escapes
        for copy in (block, escaped):
            assert add_missing_surfaces(f"Intro.\n\n{copy}", _result({surface_id: block})) == f"Intro.\n\n{block}"


def test_added_surface_is_logged_by_id_without_its_content(caplog):
    with caplog.at_level(logging.INFO, logger="agent_builder_sdk.ui_chat.a2ui"):
        add_missing_surfaces("Closing sentence.", _result({"inventory": BLOCK}))
    (record,) = caplog.records
    assert "inventory" in record.getMessage()
    assert "payments-api" not in record.getMessage() and "atx-a2ui" not in record.getMessage()


def test_surface_in_a_delivered_text_leaves_the_record_and_the_rest_is_taken_once():
    first, second = build_a2ui_block("first", BOX), build_a2ui_block("second", BOX)
    state = {SURFACES_STATE_KEY: {"first": first, "second": second}, "other": 1}
    # A cut copy cannot render, so its surface stays in the record.
    forget_surfaces_in(f"Working on it.\n\n```atx-a2ui\n{second[12:60]}...\n```\n\n{first}", state)
    assert state[SURFACES_STATE_KEY] == {"second": second}
    assert take_surfaces(state) == {"second": second}
    assert state == {"other": 1}
    assert take_surfaces(state) == {}
    forget_surfaces_in(first, state)
    assert state == {"other": 1}
