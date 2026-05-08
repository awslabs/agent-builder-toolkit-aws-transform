# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the Subagent server.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from strands.types.content import ContentBlock, Message

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.subagent_server import (
    app,
    ping,
    send_message,
    send_notification,
    start_subagent_api_server,
)


class TestPingEndpoint(unittest.TestCase):
    """Test cases for GET /ping endpoint functionality."""

    def test_ping(self):
        result = asyncio.run(ping())
        assert result == {"status": "ok"}


class TestSendNotificationEndpoint(unittest.TestCase):
    """Test cases for POST /invocations endpoint functionality."""

    @patch("agent_builder_sdk.subagent_server.logger")
    def test_send_notifications_successful_response(self, mock_logger):
        """Test the successful response from the /invocations endpoint."""
        mock_logger.info.return_value = None
        request_data = {"message": {"Test notification"}}
        response = asyncio.run(send_notification(request_data))
        mock_logger.info.assert_called_once_with("Notification received by the subagent")
        assert response == {"message": "Notification received by the subagent"}


class TestAPIServer(unittest.TestCase):
    """Test cases for API server functionality."""

    @patch("agent_builder_sdk.subagent_server.uvicorn.run")
    @patch("agent_builder_sdk.subagent_server.logger")
    def test_start_subagent_api_server_default_params(self, mock_logger, mock_uvicorn_run):
        """Test starting API server with default parameters."""

        # Create mock instances
        mock_subagent_instance = AsyncMock()

        # Call the function
        start_subagent_api_server(mock_subagent_instance)

        # Verify uvicorn.run was called with correct parameters
        mock_uvicorn_run.assert_called_once_with(app, host="0.0.0.0", port=8080)

        # Verify logging
        mock_logger.info.assert_called_once_with("Starting Subagent API server on 0.0.0.0:8080")


class TestSendMessageEndpoint(unittest.TestCase):
    """Test cases for POST /message/send endpoint functionality."""

    def test_send_message_successful_response(self):
        """Test the successful response from the /message/send endpoint."""
        from agent_builder_sdk.subagent_server import InvocationRequest

        # Setup mock subagent - create a mock response object with message attribute
        mock_response = Mock()
        mock_response.message = Message(
            content=[ContentBlock(text="Test response from subagent")], role="assistant"
        )

        mock_subagent_instance = Mock()
        mock_subagent_instance.process_message.return_value = mock_response

        # Set up app.state.subagent
        app.state.subagent = mock_subagent_instance

        # Create a proper message request
        test_message = A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test message"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
            metadata={},
            extensions=["ATX_A2A.SourceInformation"],
        )

        request = InvocationRequest(message=test_message)
        response = asyncio.run(send_message(request, mock_subagent_instance))

        # Verify response structure
        assert isinstance(response, SendMessageOutput)
        assert response.error is None
        assert response.result is not None

        # Verify the result message structure
        result_message = response.result
        assert isinstance(result_message, A2AMessage)
        assert result_message.role == "agent"
        assert result_message.messageId == "msg-123"
        assert result_message.kind == "message"
        assert result_message.contextId == "ctx-456"

        # Verify the message content
        assert len(result_message.parts) == 1
        assert result_message.parts[0]["text"] == "Test response from subagent"
        assert result_message.parts[0]["kind"] == "text"
