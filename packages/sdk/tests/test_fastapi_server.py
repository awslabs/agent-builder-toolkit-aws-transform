"""
Unit tests for the FastAPI server.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.fastapi_server import (
    app,
    ping,
    send_message,
    send_notification,
    start_api_server,
)


def test_ping():
    """Test the ping endpoint."""
    result = asyncio.run(ping())
    assert result == {"status": "ok"}


@patch("agent_builder_sdk.fastapi_server.get_notification_handler")
@pytest.mark.asyncio
async def test_send_notifications_with_handler(mock_get_handler):
    """Test notification endpoint with handler available."""
    mock_handler = AsyncMock()
    mock_handler.handle_notification.return_value = {"message": "processed"}
    mock_get_handler.return_value = mock_handler

    request_data = {"notificationType": "test"}

    response = await send_notification(request_data, mock_handler)

    assert response == {"message": "processed"}


@patch("agent_builder_sdk.fastapi_server.uvicorn.run")
def test_start_api_server_default_params(mock_uvicorn_run):
    """Test starting API server with default parameters."""
    mock_queue_service = AsyncMock()

    start_api_server(mock_queue_service)

    mock_uvicorn_run.assert_called_once_with(app, host="0.0.0.0", port=8080)


@patch("agent_builder_sdk.fastapi_server.uvicorn.run")
def test_start_api_server_with_custom_handler(mock_uvicorn_run):
    """Test starting API server with custom notification handler."""
    mock_queue_service = AsyncMock()
    mock_handler = AsyncMock()

    start_api_server(mock_queue_service, mock_handler, "127.0.0.1", 9000)

    mock_uvicorn_run.assert_called_once_with(app, host="127.0.0.1", port=9000)


class TestSendMessageEndpoint(unittest.TestCase):
    """Test cases for POST /message/send endpoint functionality."""

    @patch("agent_builder_sdk.fastapi_server.queue")
    def test_send_message_successful_response(self, mock_queue):
        """Test the successful response from the /message/send endpoint."""
        from agent_builder_sdk.fastapi_server import InvocationRequest
        from agent_builder_sdk.message_queue import QueueResponse

        # Setup mock queue
        mock_response = QueueResponse(
            request_id="req-123",
            context_id="ctx-456",
            message="Message request received by the orchestrator agent",
        )

        mock_queue.submit_request = AsyncMock(return_value="req-123")
        mock_queue.wait_for_response = AsyncMock(return_value=mock_response)

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
        response = asyncio.run(send_message(request))

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
        assert (
            result_message.parts[0]["text"] == "Message request received by the orchestrator agent"
        )
        assert result_message.parts[0]["kind"] == "text"


class TestAsyncReplyFunctionality:
    """Test cases for async reply functionality."""

    @pytest.mark.parametrize("a2a_message", ["sender-123"], indirect=["a2a_message"])
    @patch("agent_builder_sdk.fastapi_server.queue")
    @patch("agent_builder_sdk.fastapi_server.handle_delayed_response")
    async def test_send_message_timeout_triggers_async_reply(
        self, mock_delay, mock_queue, a2a_message
    ):
        """Test that timeout triggers async reply."""
        from agent_builder_sdk.fastapi_server import InvocationRequest

        # Setup mock queue to return None (timeout)
        mock_queue.submit_request = AsyncMock(return_value="req-123")
        mock_queue.wait_for_response = AsyncMock(return_value=None)

        response = await send_message(InvocationRequest(a2a_message))

        # Verify async task was created
        mock_delay.assert_called_once_with("req-123", "ctx-456", a2a_message, "sender-123")

        # Verify immediate response
        assert (
            response.result.parts[0]["text"]
            == "I'm working on your request and will get back to you shortly."
        )

    @pytest.mark.parametrize("a2a_message", ["sender-123"], indirect=["a2a_message"])
    @patch("agent_builder_sdk.fastapi_server.queue")
    @patch("agent_builder_sdk.fastapi_server.handle_delayed_response")
    async def test_send_message_timeout_without_sender(self, mock_delay, mock_queue, a2a_message):
        """Test that timeout without sender does not trigger an async reply."""
        from agent_builder_sdk.fastapi_server import InvocationRequest

        a2a_message.extensions = None
        a2a_message.metadata = None

        # Setup mock queue to return None (timeout)
        mock_queue.submit_request = AsyncMock(return_value="req-123")
        mock_queue.wait_for_response = AsyncMock(return_value=None)

        response = await send_message(InvocationRequest(a2a_message))

        mock_delay.assert_not_called()

        # Verify immediate response
        assert not response.result.parts

    @patch("agent_builder_sdk.fastapi_server.queue")
    @patch("agent_builder_sdk.fastapi_server.get_agentic_api_client")
    @patch("agent_builder_sdk.fastapi_server.get_agent_context_from_env")
    async def test_handle_delayed_response_success(
        self, mock_get_context, mock_get_client, mock_queue
    ):
        """Test successful delayed response handling."""
        from agent_builder_sdk.fastapi_server import handle_delayed_response
        from agent_builder_sdk.message_queue import QueueResponse

        # Setup mocks
        mock_queue.wait_for_response = AsyncMock(
            return_value=QueueResponse(
                request_id="req-123", context_id="ctx-456", message="Delayed response message"
            )
        )
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_context = AsyncMock()
        mock_context.to_dict.return_value = {"job_id": "job-123", "workspace_id": "ws-123"}
        mock_get_context.return_value = mock_context

        test_message = A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )

        await handle_delayed_response("req-123", "ctx-456", test_message, "sender-123")

        # Verify client was called with correct parameters
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "sender-123"

    @patch("agent_builder_sdk.fastapi_server.queue")
    @patch("agent_builder_sdk.fastapi_server.get_agentic_api_client")
    @patch("agent_builder_sdk.fastapi_server.get_agent_context_from_env")
    def test_handle_delayed_response_timeout(self, mock_get_context, mock_get_client, mock_queue):
        """Test delayed response timeout handling."""
        from agent_builder_sdk.fastapi_server import handle_delayed_response

        # Setup mocks - return None for timeout
        mock_queue.wait_for_response = AsyncMock(return_value=None)
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_context = AsyncMock()
        mock_context.to_dict.return_value = {"job_id": "job-123", "workspace_id": "ws-123"}
        mock_get_context.return_value = mock_context

        test_message = A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )

        # Run the delayed response handler
        asyncio.run(handle_delayed_response("req-123", "ctx-456", test_message))

        # Verify timeout message was sent
        mock_client.send_message.assert_called_once()
        call_kwargs = mock_client.send_message.call_args[1]
        assert call_kwargs["agentInstanceId"] == "ATX_CHAT"
        # Verify the timeout message content
        params = call_kwargs["params"]
        assert "not able to generate a response on time" in params["message"]["parts"][0]["text"]

    @patch("agent_builder_sdk.fastapi_server.queue", None)
    @patch("agent_builder_sdk.fastapi_server.logger")
    def test_handle_delayed_response_no_queue(self, mock_logger):
        """Test delayed response handling when queue is None."""
        from agent_builder_sdk.fastapi_server import handle_delayed_response

        test_message = A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )

        # Run the delayed response handler
        asyncio.run(handle_delayed_response("req-123", "ctx-456", test_message))

        # Verify error was logged
        mock_logger.error.assert_called_with("Queue is not available for delayed response handling")

    @patch("agent_builder_sdk.fastapi_server.queue")
    @patch("agent_builder_sdk.fastapi_server.logger")
    def test_handle_delayed_response_exception(self, mock_logger, mock_queue):
        """Test delayed response handling when an exception occurs."""
        from agent_builder_sdk.fastapi_server import handle_delayed_response

        # Setup mock to raise exception
        mock_queue.wait_for_response = AsyncMock(side_effect=Exception("Test error"))

        test_message = A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )

        # Run the delayed response handler
        asyncio.run(handle_delayed_response("req-123", "ctx-456", test_message))

        # Verify error was logged
        mock_logger.error.assert_called_with("Error waiting for response: Test error")
