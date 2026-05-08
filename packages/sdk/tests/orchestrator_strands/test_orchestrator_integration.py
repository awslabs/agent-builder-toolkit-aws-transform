# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import create_autospec

import pytest
from strands.models import Model

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.orchestrator_strands.hooks import ConversationHookProvider
from tests.orchestrator_strands.integration_utils import (
    TestMessage,
    create_message,
    create_stream_side_effect,
)


@pytest.fixture
def orchestrator():
    orchestrator = AsyncBaseOrchestrator("")
    # Avoid printing model outputs to stdout
    orchestrator.callback_handler = lambda *args, **kwargs: None
    orchestrator.model = create_autospec(Model, spec_set=True, instance=True)

    return orchestrator


async def test_notifications(orchestrator, tmpdir):
    """Notifications should be added to every user's conversation history."""
    user_message_1 = TestMessage("user", "1")
    notification_message = TestMessage("notification", "1", MessageSourceType.NOTIFICATION)
    user_message_2 = TestMessage("user", "2")
    subagent_message = TestMessage("subagent", "1", MessageSourceType.SUBAGENT)
    messages = {
        m.input: m for m in [user_message_1, notification_message, user_message_2, subagent_message]
    }

    orchestrator.hooks.add_hook(ConversationHookProvider(storage_dir=tmpdir))
    orchestrator.model.stream.side_effect = create_stream_side_effect(messages)

    await orchestrator.process_message_async(
        ProcessMessageRequest(
            user_message_1.input, ConversationContext(user_id=user_message_1.source_id)
        )
    )
    await orchestrator.process_message_async(
        ProcessMessageRequest(notification_message.input, ConversationContext())
    )
    await orchestrator.process_message_async(
        ProcessMessageRequest(
            user_message_2.input, ConversationContext(user_id=user_message_2.source_id)
        )
    )
    await orchestrator.process_message_async(
        ProcessMessageRequest(
            subagent_message.input,
            ConversationContext(agent_instance_id=subagent_message.source_id),
        )
    )

    assert orchestrator.model.stream.call_count == 4
    assert user_message_1.invocations[0][0] == [create_message(user_message_1.input, "user")]
    assert notification_message.invocations[0][0] == [
        create_message(notification_message.input, "user")
    ]
    assert user_message_2.invocations[0][0] == [
        create_message(user_message_1.input, "user"),
        create_message(user_message_1.output, "assistant"),
        create_message(notification_message.input, "user"),
        create_message(notification_message.output, "assistant"),
        create_message(user_message_2.input, "user"),
    ]
    assert subagent_message.invocations[0][0] == [create_message(subagent_message.input, "user")]
