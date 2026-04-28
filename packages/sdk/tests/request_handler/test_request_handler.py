"""Tests for message processing module."""

import asyncio
import unittest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.message_queue import (
    QueueRequest,
    QueueResponse,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)
from agent_builder_sdk.request_handler import RequestHandler
from agent_builder_sdk.request_handler.context import RequestContext
from agent_builder_sdk.request_handler.queue_handler import QueueRequestHandler


class TestRequestHandler(unittest.TestCase):
    """Test the abstract RequestHandler class."""

    def test_message_processor_is_abstract(self):
        """Test that RequestHandler cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            RequestHandler()

    def test_required_methods(self):
        """Test that required methods are defined in the interface."""
        # Check that the methods are defined in the interface
        self.assertTrue(
            hasattr(RequestHandler, "receive_request"), "receive_request method not defined"
        )
        self.assertTrue(
            hasattr(RequestHandler, "store_response"), "store_response method not defined"
        )


class MockProcessor(RequestHandler):
    """Mock implementation of RequestHandler for testing."""

    async def receive_request(self):
        """Mock implementation."""
        pass

    async def store_response(self, message, recipient_id=None):
        """Mock implementation."""
        pass


class TestRequestHandlerImplementation(unittest.TestCase):
    """Test an implementation of the RequestHandler."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_processor = MockProcessor()

    def test_mock_processor_receive(self):
        """Test mocked receive_request method."""
        # Create an event loop for async testing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Mock the receive_request method
            self.mock_processor.receive_request = AsyncMock(return_value={"text": "Test message"})

            # Call the method
            result = loop.run_until_complete(self.mock_processor.receive_request())

            # Check the result
            self.assertEqual(result, {"text": "Test message"})
            self.assertTrue(self.mock_processor.receive_request.called)
        finally:
            # Clean up loop
            loop.close()

    def test_mock_processor_send(self):
        """Test mocked store_response method."""
        # Create an event loop for async testing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Mock the store_response method
            self.mock_processor.store_response = AsyncMock(return_value=True)

            # Call the method
            result = loop.run_until_complete(
                self.mock_processor.store_response("Hello", "recipient-123")
            )

            # Check the result
            self.assertTrue(result)
            self.mock_processor.store_response.assert_called_with("Hello", "recipient-123")
        finally:
            # Clean up loop
            loop.close()


class TestResponseStore(ResponseStore):
    def __init__(self):
        self.responses = {}

    async def get_response(self, request_id: str) -> Optional[QueueResponse]:
        return self.responses.get(request_id)

    async def delete_response(self, request_id: str) -> bool:
        return self.responses.pop(request_id, False) or True

    async def list_responses(self, limit: Optional[int] = None) -> List[QueueResponse]:
        return list(self.responses.values())

    async def cleanup_old_responses(self, max_age_hours: int = 24) -> int:
        pass

    async def health_check(self) -> bool:
        return True

    async def store_response(self, response: QueueResponse) -> bool:
        self.responses[response.request_id] = response
        return True


# Pytest-style tests for QueueRequestHandler
@pytest.fixture
def queue_request_handler():
    """Create QueueRequestHandler instance for testing."""
    mock_request_queue = create_autospec(RequestQueue, spec_set=True, instance=True)
    return QueueRequestHandler(request_queue=mock_request_queue, response_store=TestResponseStore())


@pytest.mark.parametrize(
    ["agent_class", "process_method"],
    [
        (BaseAgent, "process_message"),
        (AsyncBaseAgent, "process_message_async"),
    ],
)
async def test_processing(queue_request_handler, agent_result, agent_class, process_method):
    request = QueueRequest(context=dict(context_id="context-id"))
    queue_request_handler.request_queue.dequeue.return_value = request

    mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
    getattr(mock_agent, process_method).side_effect = [agent_result, asyncio.CancelledError()]
    mock_get_agent = AsyncMock(return_value=mock_agent)

    await queue_request_handler.start_processing(mock_get_agent)
    response = await queue_request_handler.response_store.get_response(request.request_id)

    assert response is not None
    assert response.context_id == "context-id"
    assert response.message == "test agent result"
    assert response.status is RequestStatus.COMPLETED


@pytest.mark.asyncio
async def test_start_processing_with_factory_returning_none_async_agent(queue_request_handler):
    """Test start_processing works when checkpoint provider returns None (async agent)."""
    # Mock checkpoint provider that returns None
    mock_checkpoint_provider = MagicMock(return_value=None)

    # Mock message processing flow
    mock_message_data = {
        "request_id": "test-123",
        "message": "test message",
        "context": RequestContext(user_id="user1", context_id="ctx-123"),
        "transaction_id": "t-123",
    }

    # Mock agent with process_message_async (async path)
    mock_agent = MagicMock()
    mock_agent.process_message_async = AsyncMock(return_value="agent response")
    mock_get_agent = AsyncMock(return_value=mock_agent)

    # Mock queue_request_handler methods - process one message then cancel
    queue_request_handler.receive_request = AsyncMock(
        side_effect=[mock_message_data, asyncio.CancelledError()]
    )
    queue_request_handler.store_response = AsyncMock()

    with patch(
        "agent_builder_sdk.request_handler.queue_handler.extract_text_from_strands_agent_response",
        return_value="extracted text",
    ):
        # Test with checkpoint provider that returns None
        await queue_request_handler.start_processing(mock_get_agent, mock_checkpoint_provider)

        # Verify workflow completed
        mock_checkpoint_provider.assert_called_once()  # Provider called
        mock_agent.process_message_async.assert_called_once()  # Async message processed


@pytest.mark.asyncio
async def test_start_processing_with_factory_returning_none_sync_agent(queue_request_handler):
    """Test start_processing works when checkpoint provider returns None (sync agent)."""
    # Mock checkpoint provider that returns None
    mock_checkpoint_provider = MagicMock(return_value=None)

    # Mock message processing flow
    mock_message_data = {
        "request_id": "test-123",
        "message": "test message",
        "context": RequestContext(user_id="user1", context_id="ctx-123"),
        "transaction_id": "t-123",
    }

    # Mock agent with only process_message (sync path)
    mock_agent = MagicMock()
    mock_agent.process_message = MagicMock(return_value="agent response")
    # Ensure hasattr(agent, "process_message_async") returns False
    if hasattr(mock_agent, "process_message_async"):
        delattr(mock_agent, "process_message_async")

    mock_get_agent = AsyncMock(return_value=mock_agent)

    # Mock queue_request_handler methods - process one message then cancel
    queue_request_handler.receive_request = AsyncMock(
        side_effect=[mock_message_data, asyncio.CancelledError()]
    )
    queue_request_handler.store_response = AsyncMock()

    with patch(
        "agent_builder_sdk.request_handler.queue_handler.extract_text_from_strands_agent_response",
        return_value="extracted text",
    ):
        # Test with checkpoint provider that returns None
        await queue_request_handler.start_processing(mock_get_agent, mock_checkpoint_provider)

        # Verify workflow completed
        mock_checkpoint_provider.assert_called_once()  # Provider called
        mock_agent.process_message.assert_called_once()  # Sync message processed
