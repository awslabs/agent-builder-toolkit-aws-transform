# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import create_autospec

import pytest
from strands.agent import AgentResult
from strands.models import BedrockModel
from strands.telemetry import EventLoopMetrics
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.message_queue import QueueService
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    ConversationRepository,
)
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT
from agent_builder_types import type_defs as abt


@pytest.fixture
def mock_model():
    return create_autospec(BedrockModel, spec_set=True, instance=True)


@pytest.fixture
def mock_repository():
    return create_autospec(ConversationRepository, spec_set=True, instance=True)


@pytest.fixture
def mock_memory_manager():
    return create_autospec(MemoryManager, spec_set=True, instance=True)


@pytest.fixture
def agent_result():
    """Test processing message from a user."""
    # Create a response message
    response_content = [ContentBlock(text="test agent result")]
    response = Message(role="assistant", content=response_content)

    return AgentResult(
        message=response, stop_reason="end_turn", metrics=EventLoopMetrics(), state={}
    )


@pytest.fixture
def a2a_message(request) -> A2AMessage:
    sender = "ATX_CHAT"
    if hasattr(request, "param"):
        sender = request.param

    return A2AMessage(
        role="user",
        parts=[{"kind": "text", "text": "Test message"}],
        messageId="msg-123",
        kind="message",
        contextId="ctx-456",
        metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": sender}},
        extensions=[A2A_SOURCE_INFORMATION_EXT],
        taskId="task-789",
    )


@pytest.fixture
def mock_queue_service():
    queue_service = create_autospec(QueueService, spec_set=True, instance=True)
    queue_service.submit_request.return_value = "request-123"

    return queue_service


@pytest.fixture
def response_metadata() -> abt.ResponseMetadataTypeDef:
    return abt.ResponseMetadataTypeDef(
        RequestId="1", HostId="2", HTTPStatusCode=200, HTTPHeaders={}, RetryAttempts=0
    )
