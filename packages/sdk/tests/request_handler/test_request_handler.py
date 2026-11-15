# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for message processing module."""

import asyncio
import time
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from strands.agent import AgentResult
from strands.types.exceptions import EventLoopException

from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.message_queue import (
    QueueRequest,
    QueueResponse,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    turn_deadline,
    turn_error_note,
)
from agent_builder_sdk.request_handler import RequestHandler
from agent_builder_sdk.request_handler.context import RequestContext
from agent_builder_sdk.request_handler.queue_handler import QueueRequestHandler
from agent_builder_sdk.util.suggestions_manager import (
    clear_suggestions,
    get_and_consume_suggestions,
)


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


async def _run_one_turn_for(
    handler: QueueRequestHandler, request: QueueRequest, process: Any
) -> None:
    handler.request_queue.dequeue.side_effect = [request, asyncio.CancelledError()]
    agent = create_autospec(AsyncBaseAgent, spec_set=True, instance=True)
    agent.process_message_async.side_effect = process
    await handler.start_processing(AsyncMock(return_value=agent))


def _user_handler(**kwargs: Any) -> QueueRequestHandler:
    return QueueRequestHandler(
        request_queue=create_autospec(RequestQueue, spec_set=True, instance=True),
        response_store=TestResponseStore(),
        **kwargs,
    )


def _chat_user_request() -> QueueRequest:
    return QueueRequest(context=dict(context_id="c", user_id="user-1", sender="ATX_CHAT"))


@pytest.mark.parametrize(["sender", "remaining"], [("ATX_CHAT", 50), (None, 3)])
async def test_a_user_turn_runs_with_the_reply_deadline_counted_from_its_arrival(
    agent_result: AgentResult, sender: Optional[str], remaining: float
) -> None:
    """The deadline is the request's arrival plus the delayed wait when a sender gets the late
    reply, else plus the synchronous wait, so time spent in the queue counts against it. The
    delayed wait alone holds when an extension handler acknowledges the request at once."""
    handler = _user_handler(timeout=28, delayed_timeout=300)
    request = QueueRequest(
        context=dict(context_id="c", user_id="user-1", sender=sender),
        created_at=datetime.now(timezone.utc) - timedelta(seconds=25 if sender is None else 250),
    )
    seen: dict[str, float] = {}

    async def process(_request: Any) -> AgentResult:
        seen["remaining"] = turn_deadline.get() - time.monotonic()
        return agent_result

    await _run_one_turn_for(handler, request, process)

    assert remaining - 2 < seen["remaining"] <= remaining
    assert turn_deadline.get() is None
    assert turn_error_note.get() is None


@pytest.mark.parametrize(
    "context", [dict(context_id="c", agent_instance_id="agent-7"), dict(context_id="hitl-task-1")]
)
async def test_turns_from_other_sources_run_without_a_deadline_or_a_note(
    agent_result: AgentResult, context: dict[str, Any]
) -> None:
    handler = _user_handler()
    seen: dict[str, Any] = {}

    async def process(_request: Any) -> AgentResult:
        seen["deadline"], seen["note"] = turn_deadline.get(), turn_error_note.get()
        return agent_result

    await _run_one_turn_for(handler, QueueRequest(context=context), process)

    assert seen == {"deadline": None, "note": None}


@pytest.mark.parametrize("wrapped", [False, True])
async def test_a_user_turn_that_ends_with_a_note_stores_the_note_as_its_reply(
    wrapped: bool,
) -> None:
    """A note left for the exception that ends the turn, raised as is or inside the
    EventLoopException Strands raises after a tool call, is stored with its chip as a completed
    reply; the raw exception text reaches nobody."""
    clear_suggestions()
    handler = _user_handler()
    request = _chat_user_request()
    failure = RuntimeError('Read timeout on endpoint URL: "https://bedrock-runtime..."')

    async def process(_request: Any) -> AgentResult:
        note = turn_error_note.get()
        assert note is not None
        note.text, note.suggestions, note.exception = "Reply Continue.", ["Continue"], failure
        if wrapped:
            raise EventLoopException(failure) from failure
        raise failure

    await _run_one_turn_for(handler, request, process)

    response = await handler.response_store.get_response(request.request_id)
    assert response.status is RequestStatus.COMPLETED
    assert response.message == "Reply Continue."
    assert response.error_message is None
    assert get_and_consume_suggestions() == ["Continue"]
    handler.request_queue.update_request_status.assert_awaited_once_with(
        request.request_id, RequestStatus.COMPLETED
    )
    assert turn_error_note.get() is None


async def test_a_note_for_another_exception_does_not_mask_the_one_ending_the_turn() -> None:
    handler = _user_handler()
    request = _chat_user_request()

    async def process(_request: Any) -> AgentResult:
        note = turn_error_note.get()
        assert note is not None
        note.text, note.exception = "note", RuntimeError("inner")
        raise RuntimeError("outer")

    await _run_one_turn_for(handler, request, process)

    response = await handler.response_store.get_response(request.request_id)
    assert response.status is RequestStatus.FAILED
    assert response.error_message == "outer"


async def test_each_user_turn_gets_a_fresh_note() -> None:
    """A note left on one turn does not reach the next turn's error handling."""
    handler = _user_handler()
    first, second = _chat_user_request(), _chat_user_request()
    handler.request_queue.dequeue.side_effect = [first, second, asyncio.CancelledError()]
    agent = create_autospec(AsyncBaseAgent, spec_set=True, instance=True)
    failures = iter([RuntimeError("first"), RuntimeError("second")])

    async def process(_request: Any) -> AgentResult:
        failure = next(failures)
        note = turn_error_note.get()
        assert note is not None and note.text is None
        if str(failure) == "first":
            note.text, note.exception = "note", failure
        raise failure

    agent.process_message_async.side_effect = process
    await handler.start_processing(AsyncMock(return_value=agent))

    assert (await handler.response_store.get_response(first.request_id)).message == "note"
    assert (await handler.response_store.get_response(second.request_id)).error_message == "second"
