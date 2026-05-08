# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the SendMessageTools class."""

import uuid
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext
from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.orchestrator_strands.tools.send_message_tools import SendMessageTools
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT


@pytest.fixture
def send_message_tools():
    """Create a SendMessageTools instance."""
    return SendMessageTools()


class TestSendMessageTools:
    """Test class for SendMessageTools."""

    def test_initialization(self):
        """Test SendMessageTools initialization."""
        tools = SendMessageTools()
        assert isinstance(tools, SendMessageTools)

    def test_construct_message(self, send_message_tools):
        """Test _construct_message method."""
        message = send_message_tools._construct_message("Test message", "sender")
        assert isinstance(message, A2AMessage)
        assert message.role == "agent"
        assert message.parts == [{"kind": "text", "text": "Test message"}]
        assert message.kind == "message"
        assert message.metadata == {A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}}
        assert message.extensions == [A2A_SOURCE_INFORMATION_EXT]
        assert isinstance(message.messageId, str)
        # Verify messageId is a valid UUID
        uuid.UUID(message.messageId)

    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    def test_send_message_to_subagent_success(
        self, mock_get_context, mock_get_client, send_message_tools
    ):
        """Test successful send_message_to_subagent."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )

        # Call the tool
        result = send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify result
        assert result == mock_client.send_message.return_value

        # Verify client was called correctly
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "subagent-456"
        message_dict = call_kwargs["params"]["message"]
        assert message_dict["role"] == "agent"
        assert message_dict["parts"] == [{"kind": "text", "text": "Test message"}]
        assert message_dict["kind"] == "message"
        assert message_dict["metadata"] == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}
        }
        assert message_dict["extensions"] == [A2A_SOURCE_INFORMATION_EXT]
        assert "messageId" in message_dict
        assert call_kwargs["requestContext"] == mock_get_context.return_value.to_dict()

    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    def test_send_message_to_subagent_client_exception(self, mock_get_client, send_message_tools):
        """Test send_message_to_subagent when client raises exception."""
        # Setup mock to raise exception
        mock_get_client.side_effect = Exception("API error")

        # Call the tool and expect exception
        with pytest.raises(Exception) as exc_info:
            send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify exception message
        assert "API error" in str(exc_info.value)

    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    def test_initialization_logging(self, mock_logger):
        """Test that initialization logs appropriately."""
        SendMessageTools()
        mock_logger.info.assert_called_with("Initialized SendMessageTools")

    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    def test_success_logging(
        self, mock_get_context, mock_get_client, mock_logger, send_message_tools
    ):
        """Test that successful operations are logged appropriately."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_context = Mock()
        mock_context.to_dict.return_value = {"job_id": "job-123"}
        mock_get_context.return_value = mock_context

        # Call the tool
        send_message_tools.send_message_to_subagent("subagent-456", "Test message")

        # Verify success was logged
        mock_logger.info.assert_called_with("Message sent to subagent subagent-456.")

    @pytest.mark.asyncio
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_async_send_message_to_subagent_success(
        self, mock_get_context, mock_get_client, send_message_tools
    ):
        """Test successful async_send_message_to_subagent."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_get_context.return_value = AgenticApiRequestContext(
            "job-123", "workspace-123", "sender", "token"
        )

        # Call the async tool
        result = await send_message_tools.async_send_message_to_subagent(
            "subagent-456", "Test message"
        )

        # Verify result
        assert result == mock_client.send_message.return_value

        # Verify client was called correctly
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "subagent-456"
        message_dict = call_kwargs["params"]["message"]
        assert message_dict["role"] == "agent"
        assert message_dict["parts"] == [{"kind": "text", "text": "Test message"}]
        assert message_dict["kind"] == "message"
        assert message_dict["metadata"] == {
            A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "sender"}
        }
        assert message_dict["extensions"] == [A2A_SOURCE_INFORMATION_EXT]
        assert "messageId" in message_dict
        assert call_kwargs["requestContext"] == mock_get_context.return_value.to_dict()

    @pytest.mark.asyncio
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    async def test_async_send_message_to_subagent_client_exception(
        self, mock_get_client, send_message_tools
    ):
        """Test async_send_message_to_subagent when client raises exception."""
        # Setup mock to raise exception
        mock_get_client.side_effect = Exception("API error")

        # Call the async tool and expect exception
        with pytest.raises(Exception) as exc_info:
            await send_message_tools.async_send_message_to_subagent("subagent-456", "Test message")

        # Verify exception message
        assert "API error" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("agent_builder_sdk.orchestrator_strands.tools.send_message_tools.logger")
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agentic_api_client"
    )
    @patch(
        "agent_builder_sdk.orchestrator_strands.tools.send_message_tools.get_agent_context_from_env"
    )
    async def test_async_success_logging(
        self, mock_get_context, mock_get_client, mock_logger, send_message_tools
    ):
        """Test that successful async operations are logged appropriately."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_context = Mock()
        mock_context.to_dict.return_value = {"job_id": "job-123"}
        mock_get_context.return_value = mock_context

        # Call the async tool
        await send_message_tools.async_send_message_to_subagent("subagent-456", "Test message")

        # Verify success was logged
        mock_logger.info.assert_called_with("Message sent to subagent subagent-456.")
