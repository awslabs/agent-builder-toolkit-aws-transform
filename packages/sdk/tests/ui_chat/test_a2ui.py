# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the A2UI surface builder and its agent tools."""

import json

import pytest

from agent_builder_sdk.ui_chat import a2ui
from agent_builder_sdk.ui_chat.a2ui import (
    A2UIValidationError,
    build_a2ui_block,
    build_a2ui_messages,
    flatten,
    render_a2ui_surface,
    suggest_replies,
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
