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
from strands.hooks import BeforeModelCallEvent, BeforeToolCallEvent
from strands.models import Model
from strands.types.content import Message, Messages
from strands.types.exceptions import ContextWindowOverflowException, ModelThrottledException

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

    Prompts in ``thinking_only_replies`` get a content-filtered, thinking-only reply. The model's
    first ``tool_calls`` replies call ``lookup``, and its call number ``overflow_on_call`` fails
    with a context-window overflow.

    With ``manual_thinking`` it is configured for extended thinking with a token budget and
    checks what that mode checks: not the prefix, but that the tool call in progress starts
    with its thinking block.
    """
    model = create_autospec(Model, spec_set=True, instance=True)
    model.stateful = False  # a mock attribute is truthy, and Strands clears history for stateful models
    if manual_thinking:
        model.get_config.return_value = {"additional_request_fields": _MANUAL_THINKING}
    tool_calls_left = tool_calls

    async def stream(
        messages: Messages, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        nonlocal tool_calls_left
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
        if tool_calls_left:
            tool_calls_left -= 1
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
    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))

    user, notification = ConversationContext(user_id="user"), ConversationContext()
    for text, context in [("u1", user), ("n1", notification), ("u2", user), ("u3", user)]:
        await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert orchestrator.model.stream.call_count == 4


async def test_new_agent_on_a_stored_conversation_replays_no_stale_thinking(tmp_path: Path) -> None:
    model = _prefix_checking_model()
    user, notification = ConversationContext(user_id="user"), ConversationContext()

    # The second orchestrator stands for a process restart: it has seen no earlier model call,
    # so only the strip at invocation start protects u2.
    for turns in ([("u1", user), ("n1", notification)], [("u2", user)]):
        orchestrator = AsyncBaseOrchestrator("")
        orchestrator.callback_handler = lambda *args, **kwargs: None
        orchestrator.model = model
        # Added after construction on purpose: the strip must still run after the history swap.
        orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))
        for text, context in turns:
            await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert model.stream.call_count == 3


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


@pytest.mark.parametrize("manual_thinking", [False, True], ids=["prefix-bound", "manual"])
async def test_resume_after_a_tool_interrupt_replays_a_valid_tool_call(
    manual_thinking: bool,
) -> None:
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model(tool_calls=1, manual_thinking=manual_thinking)

    def ask_first(event: BeforeToolCallEvent) -> None:
        event.interrupt("approval")

    subagent.hooks.add_callback(BeforeToolCallEvent, ask_first)

    # The interrupt ends the invocation on the tool call; the resume is a new invocation.
    interrupted = await subagent.invoke_async("go")
    assert [next(iter(block)) for block in subagent.messages[-1]["content"]] == [
        "reasoningContent",
        "toolUse",
    ]
    resumed = await subagent.invoke_async(
        [
            {"interruptResponse": {"interruptId": interrupt.id, "response": "yes"}}
            for interrupt in interrupted.interrupts
        ]
    )

    assert (interrupted.stop_reason, resumed.stop_reason) == ("interrupt", "end_turn")


async def test_subagent_replays_no_stale_thinking_after_a_trim_inside_a_tool_loop() -> None:
    subagent = AsyncBaseSubagent(
        "",
        custom_tools=[lookup],
        conversation_manager=SlidingWindowConversationManager(window_size=4, per_turn=True),
    )
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model(tool_calls=5)

    await subagent.process_message_async("go")

    assert subagent.model.stream.call_count == 6


async def test_subagent_replays_no_stale_thinking_after_a_late_hook_trims_a_tool_loop() -> None:
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model(tool_calls=3)

    def drop_oldest_tool_round(event: BeforeModelCallEvent) -> None:
        if len(event.agent.messages) > 4:
            del event.agent.messages[1:3]

    # Added after construction on purpose: the strip must still run after this trim.
    subagent.hooks.add_callback(BeforeModelCallEvent, drop_oldest_tool_round)

    await subagent.process_message_async("go")

    assert subagent.model.stream.call_count == 4


async def test_tool_loop_keeps_its_thinking_while_history_only_grows() -> None:
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model(tool_calls=2)

    await subagent.process_message_async("go")

    replies = [m["content"] for m in subagent.messages if m["role"] == "assistant"]
    assert len(replies) == 3 and all("reasoningContent" in reply[0] for reply in replies)


def _agent(messages: Messages, config: Any = None) -> SimpleNamespace:
    model = create_autospec(Model, spec_set=True, instance=True)
    model.get_config.return_value = config
    return SimpleNamespace(model=model, messages=messages)


def _tool_call() -> Message:
    return {"role": "assistant", "content": [_THINKING, {"toolUse": {"toolUseId": "t1"}}]}


@pytest.mark.parametrize(
    ("change", "kept"),
    [
        (lambda messages: messages.append({"role": "user", "content": [{"text": "more"}]}), True),
        (lambda messages: messages.pop(0), False),
        (lambda messages: messages.__setitem__(0, dict(messages[0])), False),
    ],
    ids=["appended", "trimmed", "first-message-replaced"],
)
def test_model_call_strip_follows_a_changed_prefix(change: Any, kept: bool) -> None:
    agent = _agent([{"role": "user", "content": [{"text": "u1"}]}, _tool_call()])
    hook = _StripReplayedThinking()
    hook._strip_after_history_change(SimpleNamespace(agent=agent))
    assert _THINKING in agent.messages[1]["content"]

    change(agent.messages)
    hook._strip_after_history_change(SimpleNamespace(agent=agent))

    assert any(_THINKING in message["content"] for message in agent.messages) is kept


@pytest.mark.parametrize(
    "exception", [None, ModelThrottledException("slow down")], ids=["no-error", "throttled"]
)
def test_model_call_without_an_overflow_keeps_thinking(exception: Exception | None) -> None:
    agent = _agent([_tool_call()])

    _StripReplayedThinking._strip_before_overflow_retry(
        SimpleNamespace(agent=agent, exception=exception)
    )

    assert _THINKING in agent.messages[0]["content"]


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
    agent = _agent([_tool_call()], config)
    overflow = ContextWindowOverflowException("Input is too long for requested model")

    _StripReplayedThinking._strip_before_overflow_retry(
        SimpleNamespace(agent=agent, exception=overflow)
    )

    assert (_THINKING in agent.messages[0]["content"]) is kept


def test_strip_rewrites_only_messages_with_thinking_in_place() -> None:
    user = {"role": "user", "content": [{"text": "u1"}]}
    thinking_only = {"role": "assistant", "content": [_THINKING]}
    reply = {"role": "assistant", "content": [_THINKING, {"text": "a2"}]}
    messages = [user, thinking_only, {"role": "user", "content": [{"text": "u2"}]}, reply]
    agent = _agent(messages)

    _StripReplayedThinking._strip(SimpleNamespace(agent=agent))

    assert agent.messages is messages and messages[0] is user
    # The conversation repository can hold these same objects, so they keep their thinking.
    assert thinking_only["content"] == [_THINKING]
    assert reply["content"] == [_THINKING, {"text": "a2"}]
    assert [m["content"] for m in messages] == [
        [{"text": "u1"}],
        [{"text": "[blank text]"}],
        [{"text": "u2"}],
        [{"text": "a2"}],
    ]


def test_blank_reply_hook_reads_a_stripped_thinking_only_turn_as_blank() -> None:
    agent = _agent([{"role": "assistant", "content": [_THINKING]}])

    _StripReplayedThinking._strip(SimpleNamespace(agent=agent))

    assert blank_reply_hook_provider._is_blank(agent.messages[0])
    # One object, not two equal literals that can drift apart.
    assert blank_reply_hook_provider._BLANK_TEXT_SENTINEL is _BLANK_TEXT_SENTINEL
