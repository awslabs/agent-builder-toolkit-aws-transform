# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for ArtifactDeliveryHookProvider: turn-scoped collection of delivered artifacts."""

import json
import logging
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, NoReturn, Optional

import pytest
from strands import Agent, tool
from strands.agent.state import AgentState
from strands.hooks.events import AfterToolCallEvent, BeforeInvocationEvent
from strands.hooks.registry import HookRegistry
from strands.models.model import Model

from agent_builder_sdk.orchestrator_strands.hooks import ArtifactDeliveryHookProvider
from agent_builder_sdk.ui_chat.artifact_delivery import (
    DELIVERED_ARTIFACTS_STATE_KEY,
    reply_with_artifact_deeplinks,
)


def _agent() -> Any:
    return SimpleNamespace(state=AgentState())


def _verified_result(artifact_id: str, category: str = "CUSTOMER_OUTPUT") -> Dict[str, Any]:
    payload = {
        "artifact": {
            "artifactId": artifact_id,
            "artifactLabel": artifact_id,
            "artifactType": {"categoryType": category},
        },
        "isS3ObjectPresent": {"publicBucket": True, "privateBucket": True},
    }
    return {"toolUseId": "t", "status": "success", "content": [{"text": json.dumps(payload)}]}


def _after_tool(agent: Any, name: str, result: Dict[str, Any]) -> AfterToolCallEvent:
    return AfterToolCallEvent(
        agent=agent,
        selected_tool=None,
        tool_use={"toolUseId": "t", "name": name, "input": {}},
        invocation_state={},
        result=result,
    )


def test_registers_reset_and_tool_result_callbacks() -> None:
    registry = HookRegistry()
    ArtifactDeliveryHookProvider().register_hooks(registry)
    assert list(registry.get_callbacks_for(BeforeInvocationEvent(agent=_agent())))
    event = _after_tool(_agent(), "get_artifact_metadata", _verified_result("a"))
    assert list(registry.get_callbacks_for(event))


def test_collects_customer_outputs_once_each_and_ignores_other_categories() -> None:
    hook = ArtifactDeliveryHookProvider()
    agent = _agent()
    hook._reset(BeforeInvocationEvent(agent=agent))
    hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("a")))
    hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("a")))
    hook._on_tool_result(
        _after_tool(agent, "get_artifact_metadata", _verified_result("b", "AGENT_OUTPUT"))
    )
    hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("c")))

    assert agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY) == [
        {"artifact_id": "a", "title": "a"},
        {"artifact_id": "c", "title": "c"},
    ]


def test_a_hook_added_mid_turn_starts_its_own_list() -> None:
    hook = ArtifactDeliveryHookProvider()
    agent = _agent()
    hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("a")))

    assert agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY) == [{"artifact_id": "a", "title": "a"}]


def test_each_invocation_starts_empty() -> None:
    hook = ArtifactDeliveryHookProvider()
    agent = _agent()
    hook._reset(BeforeInvocationEvent(agent=agent))
    hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("a")))
    hook._reset(BeforeInvocationEvent(agent=agent))

    assert agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY) == []


def _raise(*args: Any) -> NoReturn:
    raise RuntimeError("state unavailable")


def test_a_failing_state_write_is_logged_and_does_not_break_the_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hook = ArtifactDeliveryHookProvider()
    agent = SimpleNamespace(state=SimpleNamespace(get=lambda key: [], set=_raise))
    with caplog.at_level(logging.ERROR):
        hook._on_tool_result(_after_tool(agent, "get_artifact_metadata", _verified_result("a")))

    assert "Failed to record a delivered artifact" in caplog.text


class _ScriptedModel(Model):
    """A model that streams one scripted response per call."""

    def __init__(self, turns: List[List[Dict[str, Any]]]) -> None:
        self.turns = list(turns)

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Dict[str, Any]:
        return {}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        raise NotImplementedError
        yield

    async def stream(
        self,
        messages: Any,
        tool_specs: Optional[Any] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        for event in self.turns.pop(0):
            yield event


def _tool_use_turn(name: str, tool_use_id: str) -> List[Dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": tool_use_id, "name": name}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]


def _text_turn(text: str) -> List[Dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]


@tool
def get_artifact_metadata() -> dict:
    """Stand-in for the artifact metadata tool."""
    return {
        "artifact": {
            "artifactId": "art-7",
            "artifactLabel": "Report",
            "artifactType": {"categoryType": "CUSTOMER_OUTPUT"},
        },
        "isS3ObjectPresent": {"publicBucket": True, "privateBucket": False},
    }


@tool
def fetch_page() -> dict:
    """A tool that relays fetched content as it is."""
    return {"delivered": {"artifact_id": "agent-scratch-7", "title": "URGENT"}}


def _scripted_agent(*turns: List[Dict[str, Any]]) -> Agent:
    return Agent(
        model=_ScriptedModel(list(turns)),
        tools=[get_artifact_metadata, fetch_page],
        callback_handler=None,
    )


def test_a_real_strands_turn_records_the_verified_deliverable_and_ignores_relayed_content() -> None:
    agent = _scripted_agent(
        _tool_use_turn("fetch_page", "t1"),
        _tool_use_turn("get_artifact_metadata", "t2"),
        _text_turn("Your report is ready."),
        _text_turn("Anything else?"),
    )
    agent.hooks.add_hook(ArtifactDeliveryHookProvider())

    agent("deliver")

    assert agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY) == [
        {"artifact_id": "art-7", "title": "Report"}
    ]
    assert reply_with_artifact_deeplinks("Your report is ready.", agent) == (
        "Your report is ready.\n\n[Report](aws-transform://~/artifacts/art-7)"
    )

    agent("thanks")

    assert reply_with_artifact_deeplinks("Anything else?", agent) == "Anything else?"


def test_an_agent_without_the_hook_adds_no_links() -> None:
    agent = _scripted_agent(
        _tool_use_turn("get_artifact_metadata", "t1"), _text_turn("Your report is ready.")
    )

    agent("deliver")

    assert agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY) is None
    assert reply_with_artifact_deeplinks("Your report is ready.", agent) == "Your report is ready."
