# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""A replayed thinking block must sit behind the same prefix it was produced under.

Claude 5.5 models reject (HTTP 400) a thinking block whose earlier messages changed. The fake
model below applies that check, so these tests fail if the SDK replays reordered or trimmed
history with its thinking still attached.
"""

import hashlib
import json
from unittest.mock import create_autospec

from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import Model

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider


def _prefix_signature(messages):
    visible = [
        (m["role"], [b for b in m["content"] if "reasoningContent" not in b]) for m in messages
    ]
    return hashlib.sha256(json.dumps(visible, sort_keys=True, default=str).encode()).hexdigest()


def _prefix_checking_model():
    model = create_autospec(Model, spec_set=True, instance=True)
    model.stateful = False  # a mock attribute is truthy, and Strands clears history for stateful models

    async def stream(messages, *args, **kwargs):
        for i, message in enumerate(messages):
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


async def test_subagent_replays_no_stale_thinking_after_trim():
    subagent = AsyncBaseSubagent(
        "", conversation_manager=SlidingWindowConversationManager(window_size=2)
    )
    subagent.callback_handler = lambda *args, **kwargs: None
    subagent.model = _prefix_checking_model()

    for text in ["t1", "t2", "t3"]:
        await subagent.process_message_async(text)

    assert subagent.model.stream.call_count == 3
