# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A replayed thinking block must sit behind the same prefix it was produced under.

Claude 5.5 models reject (HTTP 400) a thinking block whose earlier messages changed. The fake
model below applies that check, so these tests fail if the SDK replays reordered or trimmed
history with its thinking still attached.
"""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import create_autospec

from strands import tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import Model
from strands.types.exceptions import ContextWindowOverflowException

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider
from agent_builder_sdk.utils import _StripReplayedThinking


def _prefix_signature(messages):
    visible = [
        (m["role"], [b for b in m["content"] if "reasoningContent" not in b]) for m in messages
    ]
    return hashlib.sha256(json.dumps(visible, sort_keys=True, default=str).encode()).hexdigest()


@tool
def lookup() -> str:
    """Return a large result."""
    return "x" * 5000


def _prefix_checking_model(thinking_only_replies=(), tool_calls=0, overflow_on_call=None):
    """Fake model that checks thinking blocks like Bedrock does.

    Prompts in ``thinking_only_replies`` get a content-filtered, thinking-only reply. The model
    calls ``lookup`` until the history holds ``tool_calls`` tool results, and its call number
    ``overflow_on_call`` fails with a context-window overflow.
    """
    model = create_autospec(Model, spec_set=True, instance=True)
    model.stateful = False  # a mock attribute is truthy, and Strands clears history for stateful models

    async def stream(messages, *args, **kwargs):
        if model.stream.call_count == overflow_on_call:
            raise ContextWindowOverflowException("Input is too long for requested model")
        for i, message in enumerate(messages):
            assert message["content"], f"messages.{i}: content is empty"
            for block in message["content"]:
                if "reasoningContent" in block:
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


async def test_orchestrator_with_notifications_replays_no_stale_thinking(tmp_path):
    orchestrator = AsyncBaseOrchestrator("")
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = _prefix_checking_model()
    # Added after construction on purpose: the strip must still run after the history swap.
    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))

    user, notification = ConversationContext(user_id="user"), ConversationContext()
    for text, context in [("u1", user), ("n1", notification), ("u2", user), ("u3", user)]:
        await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert orchestrator.model.stream.call_count == 4


async def test_orchestrator_recovers_from_a_thinking_only_reply(tmp_path):
    orchestrator = AsyncBaseOrchestrator("")
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = _prefix_checking_model(thinking_only_replies={"u2"})
    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=str(tmp_path)))

    user, notification = ConversationContext(user_id="user"), ConversationContext()
    for text, context in [("u1", user), ("n1", notification), ("u2", user), ("u3", user)]:
        await orchestrator.process_message_async(ProcessMessageRequest(text, context))

    assert orchestrator.model.stream.call_count == 4


async def test_subagent_replays_no_stale_thinking_after_trim():
    subagent = AsyncBaseSubagent(
        "", conversation_manager=SlidingWindowConversationManager(window_size=2)
    )
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model()

    for text in ["t1", "t2", "t3"]:
        await subagent.process_message_async(text)

    assert subagent.model.stream.call_count == 3


async def test_subagent_survives_context_overflow_inside_a_tool_loop():
    subagent = AsyncBaseSubagent("", custom_tools=[lookup])
    subagent.callback_handler = lambda *args, **kwargs: None
    # Two tool calls, then the third model call overflows; Strands truncates a tool result and retries.
    subagent.model = _prefix_checking_model(tool_calls=2, overflow_on_call=3)

    await subagent.process_message_async("go")

    assert subagent.model.stream.call_count == 4


def test_strip_rewrites_only_messages_with_thinking_in_place():
    thinking = {"reasoningContent": {"reasoningText": {"text": "", "signature": "sig"}}}
    user = {"role": "user", "content": [{"text": "u1"}]}
    messages = [
        user,
        {"role": "assistant", "content": [thinking]},
        {"role": "user", "content": [{"text": "u2"}]},
        {"role": "assistant", "content": [thinking, {"text": "a2"}]},
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
