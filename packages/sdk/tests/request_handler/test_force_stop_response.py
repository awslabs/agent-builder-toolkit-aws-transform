"""Tests for force_stop_response handling in QueueRequestHandler and MessageHandler."""

import asyncio
from unittest.mock import AsyncMock, create_autospec

import pytest
from strands.agent import AgentResult
from strands.telemetry import EventLoopMetrics
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.message_queue import (
    QueueRequest,
    QueueResponse,
    RequestQueue,
    RequestStatus,
    ResponseStore,
)
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.request_handler.queue_handler import QueueRequestHandler
from agent_builder_sdk.utils import A2A_SOURCE_INFORMATION_EXT


class InMemoryResponseStore(ResponseStore):
    """Simple in-memory response store for testing."""

    def __init__(self):
        self.responses = {}

    async def store_response(self, response: QueueResponse) -> bool:
        self.responses[response.request_id] = response
        return True

    async def get_response(self, request_id: str):
        return self.responses.get(request_id)

    async def delete_response(self, request_id: str) -> bool:
        return self.responses.pop(request_id, False) or True

    async def list_responses(self, limit=None):
        return list(self.responses.values())

    async def cleanup_old_responses(self, max_age_hours=24):
        pass

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def queue_handler():
    mock_request_queue = create_autospec(RequestQueue, spec_set=True, instance=True)
    return QueueRequestHandler(
        request_queue=mock_request_queue, response_store=InMemoryResponseStore()
    )


def _make_agent_result(text="test response", state=None):
    """Helper to create an AgentResult simulating what Strands produces at the end of an event loop.

    Args:
        text: If provided, creates a message with a text ContentBlock (normal LLM response).
              If None, creates a message with a toolUse block (simulates stop_event_loop case).
        state: Maps to AgentResult.state, which is invocation_state["request_state"] from the
               event loop. This is where force_stop_response and stop_event_loop live.
    """
    content = (
        [ContentBlock(text=text)]
        if text
        else [{"toolUse": {"toolUseId": "t1", "name": "some_tool", "input": {}}}]
    )
    return AgentResult(
        message=Message(role="assistant", content=content),
        stop_reason="end_turn" if text else "tool_use",
        metrics=EventLoopMetrics(),
        state=state or {},
    )


class TestQueueHandlerForceStopResponse:
    """Tests for force_stop_response in QueueRequestHandler."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_force_stop_response_used_when_present(
        self, queue_handler, agent_class, process_method
    ):
        """When force_stop_response is in state, it should be used as the response text."""
        # Simulate stop_event_loop: message has a toolUse block (no text),
        # and state carries the subagent's actual response
        result = _make_agent_result(
            text=None,  # No text in message (toolUse block)
            state={"stop_event_loop": True, "force_stop_response": "Subagent says hello"},
        )

        # Set up a fake request in the queue
        request = QueueRequest(context=dict(context_id="ctx-1"))
        queue_handler.request_queue.dequeue.return_value = request

        # Mock the agent: return our result on first call, then cancel to exit the loop
        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).side_effect = [result, asyncio.CancelledError()]
        mock_get_agent = AsyncMock(return_value=mock_agent)

        # Run the queue handler — it dequeues, processes, and stores the response
        await queue_handler.start_processing(mock_get_agent)

        # Verify the stored response uses force_stop_response, not the empty message text
        response = await queue_handler.response_store.get_response(request.request_id)
        assert response is not None
        assert response.message == "Subagent says hello"
        assert response.status is RequestStatus.COMPLETED

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_force_stop_response_overrides_llm_text(
        self, queue_handler, agent_class, process_method
    ):
        """When force_stop_response is set, it takes priority over any LLM text in the message."""
        # The LLM emitted preamble text ("LLM preamble text") alongside the toolUse block,
        # but force_stop_response should take priority
        result = _make_agent_result(
            text="LLM preamble text",
            state={"stop_event_loop": True, "force_stop_response": "Actual subagent response"},
        )

        request = QueueRequest(context=dict(context_id="ctx-2"))
        queue_handler.request_queue.dequeue.return_value = request

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).side_effect = [result, asyncio.CancelledError()]
        mock_get_agent = AsyncMock(return_value=mock_agent)

        await queue_handler.start_processing(mock_get_agent)
        response = await queue_handler.response_store.get_response(request.request_id)

        # Should use force_stop_response, not the LLM's preamble text
        assert response is not None
        assert response.message == "Actual subagent response"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_normal_response_when_no_force_stop(
        self, queue_handler, agent_class, process_method
    ):
        """Without force_stop_response, normal text extraction should work as before."""
        # Normal flow: LLM produced text, no force_stop in state
        result = _make_agent_result(text="Normal LLM response", state={})

        request = QueueRequest(context=dict(context_id="ctx-3"))
        queue_handler.request_queue.dequeue.return_value = request

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).side_effect = [result, asyncio.CancelledError()]
        mock_get_agent = AsyncMock(return_value=mock_agent)

        await queue_handler.start_processing(mock_get_agent)
        response = await queue_handler.response_store.get_response(request.request_id)

        # Regression check: normal text extraction still works
        assert response is not None
        assert response.message == "Normal LLM response"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_empty_response_when_no_text_and_no_force_stop(
        self, queue_handler, agent_class, process_method
    ):
        """Without force_stop_response and no text, response should be empty."""
        # Edge case: toolUse block with no text AND no force_stop_response
        result = _make_agent_result(text=None, state={})

        request = QueueRequest(context=dict(context_id="ctx-4"))
        queue_handler.request_queue.dequeue.return_value = request

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).side_effect = [result, asyncio.CancelledError()]
        mock_get_agent = AsyncMock(return_value=mock_agent)

        await queue_handler.start_processing(mock_get_agent)
        response = await queue_handler.response_store.get_response(request.request_id)

        # No text and no force_stop_response — response should be empty
        assert response is not None
        assert response.message == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_force_stop_response_with_none_state(
        self, queue_handler, agent_class, process_method
    ):
        """When state is None, should not crash and fall back to normal extraction."""
        # Safety check: state could be None in edge cases
        result = _make_agent_result(text="Fallback text", state=None)

        request = QueueRequest(context=dict(context_id="ctx-5"))
        queue_handler.request_queue.dequeue.return_value = request

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).side_effect = [result, asyncio.CancelledError()]
        mock_get_agent = AsyncMock(return_value=mock_agent)

        await queue_handler.start_processing(mock_get_agent)
        response = await queue_handler.response_store.get_response(request.request_id)

        # Should not crash on None state, and fall back to normal text extraction
        assert response is not None
        assert response.message == "Fallback text"


@pytest.fixture
def a2a_message():
    return A2AMessage(
        role="user",
        parts=[{"kind": "text", "text": "Test message"}],
        messageId="msg-123",
        kind="message",
        contextId="ctx-456",
        metadata={A2A_SOURCE_INFORMATION_EXT: {"senderAgentInstanceId": "ATX_CHAT"}},
        extensions=[A2A_SOURCE_INFORMATION_EXT],
        taskId="task-789",
    )


class TestMessageHandlerForceStopResponse:
    """Tests for force_stop_response in MessageHandler._process_direct."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_force_stop_response_used_in_direct_processing(
        self, a2a_message, agent_class, process_method
    ):
        """When force_stop_response is in agent result state, it should be returned as the response."""
        # Simulate stop_event_loop in direct processing path
        result = _make_agent_result(
            text=None,
            state={"stop_event_loop": True, "force_stop_response": "Direct subagent response"},
        )

        # Create a mock agent and wire it into the MessageHandler
        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).return_value = result
        handler = MessageHandler(agent=mock_agent)

        # Process the message through the direct (non-queue) path
        response = await handler.send_message(InvocationRequest(a2a_message))

        # Verify force_stop_response was used as the response text
        assert response.error is None
        assert response.result is not None
        response_text = next(
            (p["text"] for p in response.result.parts if p.get("kind") == "text"), None
        )
        assert response_text == "Direct subagent response"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_force_stop_overrides_llm_text_in_direct_processing(
        self, a2a_message, agent_class, process_method
    ):
        """force_stop_response should take priority over LLM text in direct processing."""
        # LLM produced text, but force_stop_response should override it
        result = _make_agent_result(
            text="LLM said something",
            state={"force_stop_response": "Subagent override"},
        )

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).return_value = result
        handler = MessageHandler(agent=mock_agent)

        response = await handler.send_message(InvocationRequest(a2a_message))

        # Should use force_stop_response, not the LLM text
        assert response.error is None
        response_text = next(
            (p["text"] for p in response.result.parts if p.get("kind") == "text"), None
        )
        assert response_text == "Subagent override"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class,process_method",
        [
            (BaseAgent, "process_message"),
            (AsyncBaseAgent, "process_message_async"),
        ],
    )
    async def test_normal_response_without_force_stop_in_direct(
        self, a2a_message, agent_class, process_method
    ):
        """Without force_stop_response, normal text extraction should work."""
        # Normal flow: no force_stop, LLM produced text
        result = _make_agent_result(text="Normal response", state={})

        mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
        getattr(mock_agent, process_method).return_value = result
        handler = MessageHandler(agent=mock_agent)

        response = await handler.send_message(InvocationRequest(a2a_message))

        # Regression check: normal text extraction still works in direct path
        assert response.error is None
        response_text = next(
            (p["text"] for p in response.result.parts if p.get("kind") == "text"), None
        )
        assert response_text == "Normal response"
