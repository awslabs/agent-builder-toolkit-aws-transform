# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A replayed thinking block must sit behind the same prefix it was produced under.

Claude 5.5 models reject (HTTP 400) a thinking block whose earlier messages changed. The fake
model below applies that check, so these tests fail if the SDK replays reordered or trimmed
history with its thinking still attached.
"""

import hashlib
import json
from collections.abc import AsyncGenerator, Collection
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import create_autospec

import pytest
from strands import tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import Model
from strands.types.content import Messages
from strands.types.exceptions import ContextWindowOverflowException

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.hooks import (
    ConversationHookProvider,
    blank_reply_hook_provider,
)
from agent_builder_sdk.utils import _BLANK_TEXT_SENTINEL, _StripReplayedThinking

_THINKING = {"reasoningContent": {"reasoningText": {"text": "", "signature": "sig"}}}
_MANUAL_THINKING = {"thinking": {"type": "enabled", "budget_tokens": 1024}}


def _prefix_signature(messages: Messages) -> str:
    visible = [
        (m["role"], [b for b in m["content"] if "reasoningContent" not in b]) for m in messages
    ]
    return hashlib.sha256(json.dumps(visible, sort_keys=True, default=str).encode()).hexdigest()


@tool
def lookup() -> str:
    """Return a large result."""
    return "x" * 5000


def _prefix_checking_model(
    thinking_only_replies: Collection[str] = (),
    tool_calls: int = 0,
    overflow_on_call: int | None = None,
    manual_thinking: bool = False,
) -> Any:
    """Fake model that checks thinking blocks like Bedrock does.

    Prompts in ``thinking_only_replies`` get a content-filtered, thinking-only reply. The model
    calls ``lookup`` until the history holds ``tool_calls`` tool results, and its call number
    ``overflow_on_call`` fails with a context-window overflow.

    With ``manual_thinking`` it is configured for extended thinking with a token budget and
    checks what that mode checks: not the prefix, but that the tool call in progress starts
    with its thinking block.
    """
    model = create_autospec(Model, spec_set=True, instance=True)
    model.stateful = False  # a mock attribute is truthy, and Strands clears history for stateful models
    if manual_thinking:
        model.get_config.return_value = {"additional_request_fields": _MANUAL_THINKING}

    async def stream(
        messages: Messages, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        if model.stream.call_count == overflow_on_call:
            raise ContextWindowOverflowException("Input is too long for requested model")
        if manual_thinking and "toolResult" in messages[-1]["content"][0]:
            assert "reasoningContent" in messages[-2]["content"][0], (
                "the final assistant message must start with a thinking block"
            )
        for i, message in enumerate(messages):
            assert message["content"], f"messages.{i}: content is empty"
            for block in message["content"]:
                if "reasoningContent" in block and not manual_thinking:
                    signature = block["reasoningContent"]["reasoningText"]["signature"]
                    assert signature == _prefix_signature(messages[:i]), (
                        f"messages.{i}: thinking block is bound to a different conversation"
                    )
        yield {"contentBlockStart": {"start": {}}}
        yield {
            "contentBlockDelta": {
                "delta": {"reasoningContent": {"signature": _prefix_signature(messages)}}
            }
        }
        yield {"contentBlockStop": {}}
        if messages[-1]["content"][-1].get("text") in thinking_only_replies:
            yield {"messageStop": {"stopReason": "content_filtered"}}
            return
        if sum("toolResult" in block for m in messages for block in m["content"]) < tool_calls:
            tool_use = {"toolUseId": f"t{model.stream.call_count}", "name": "lookup"}
            yield {"contentBlockStart": {"start": {"toolUse": tool_use}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            return
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": "ok"}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    model.stream.side_effect = stream
    return model


async def test_orchestrator_with_notifications_replays_no_stale_thinking(tmp_path: Path) -> None:
    orchestrator = AsyncBaseOrchestrator("")
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = _prefix_checking_model()
    # Added after construction on purpose: the strip must still run after the history swap.
    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))

    user, notification = ConversationContext(user_id="user"), ConversationContext()
    for text, context in [("u1", user), ("n1", notification), ("u2", user), ("u3", user)]:
        await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert orchestrator.model.stream.call_count == 4


async def test_orchestrator_recovers_from_a_thinking_only_reply(tmp_path: Path) -> None:
    orchestrator = AsyncBaseOrchestrator("")
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = _prefix_checking_model(thinking_only_replies={"u2"})
    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))

    user, notification = ConversationContext(user_id="user"), ConversationContext()
    for text, context in [("u1", user), ("n1", notification), ("u2", user), ("u3", user)]:
        await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert orchestrator.model.stream.call_count == 4


async def test_subagent_replays_no_stale_thinking_after_trim() -> None:
    subagent = AsyncBaseSubagent(
        "", conversation_manager=SlidingWindowConversationManager(window_size=2)
    )
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model()

    for text in ["t1", "t2", "t3"]:
        await subagent.process_message_async(text)

    assert subagent.model.stream.call_count == 3


async def test_subagent_survives_context_overflow_inside_a_tool_loop() -> None:
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    # Two tool calls, then the third model call overflows; Strands truncates a tool result and retries.
    subagent.model = _prefix_checking_model(tool_calls=2, overflow_on_call=3)

    await subagent.process_message_async("go")

    assert subagent.model.stream.call_count == 4


async def test_manual_thinking_keeps_the_tool_calls_thinking_through_an_overflow_retry() -> None:
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model(tool_calls=2, overflow_on_call=3, manual_thinking=True)

    await subagent.process_message_async("go")

    assert subagent.model.stream.call_count == 4


@pytest.mark.parametrize(
    ("config", "kept"),
    [
        ({"additional_request_fields": _MANUAL_THINKING}, True),
        ({"additional_request_fields": {"thinking": {"type": "adaptive"}}}, False),
        ({"additional_request_fields": None}, False),
        ({}, False),
        (None, False),
    ],
    ids=["manual", "adaptive", "no-request-fields", "no-thinking-setting", "config-not-a-mapping"],
)
def test_overflow_strip_spares_only_manual_thinking(config: Any, kept: bool) -> None:
    model = create_autospec(Model, spec_set=True, instance=True)
    model.get_config.return_value = config
    tool_call = {"role": "assistant", "content": [_THINKING, {"toolUse": {"toolUseId": "t1"}}]}
    agent = SimpleNamespace(model=model, messages=[tool_call])
    overflow = ContextWindowOverflowException("Input is too long for requested model")

    _StripReplayedThinking._strip_before_overflow_retry(
        SimpleNamespace(agent=agent, exception=overflow)
    )

    assert (_THINKING in agent.messages[0]["content"]) is kept


def test_strip_rewrites_only_messages_with_thinking_in_place() -> None:
    user = {"role": "user", "content": [{"text": "u1"}]}
    messages = [
        user,
        {"role": "assistant", "content": [_THINKING]},
        {"role": "user", "content": [{"text": "u2"}]},
        {"role": "assistant", "content": [_THINKING, {"text": "a2"}]},
    ]
    agent = SimpleNamespace(messages=messages)

    _StripReplayedThinking._strip(SimpleNamespace(agent=agent))

    assert agent.messages is messages and messages[0] is user
    assert [m["content"] for m in messages] == [
        [{"text": "u1"}],
        [{"text": "[blank text]"}],
        [{"text": "u2"}],
        [{"text": "a2"}],
    ]


def test_blank_reply_hook_reads_a_stripped_thinking_only_turn_as_blank() -> None:
    agent = SimpleNamespace(messages=[{"role": "assistant", "content": [_THINKING]}])

    _StripReplayedThinking._strip(SimpleNamespace(agent=agent))

    assert blank_reply_hook_provider._is_blank(agent.messages[0])
    # One object, not two equal literals that can drift apart.
    assert blank_reply_hook_provider._BLANK_TEXT_SENTINEL is _BLANK_TEXT_SENTINEL
