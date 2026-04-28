"""
Unit tests for the messages handler.
"""

import json
from unittest.mock import Mock, create_autospec, patch

import pytest

from agent_builder_sdk.custom_types.common_types import InvocationRequest
from agent_builder_sdk.extensions.acknowledgments.acknowledgment_handler import (
    AcknowledgmentHandler,
)
from agent_builder_sdk.interfaces import AsyncBaseAgent, BaseAgent
from agent_builder_sdk.message_queue import QueueResponse
from agent_builder_sdk.message_queue.interface import RequestPriority
from agent_builder_sdk.messages.message_handler import MessageHandler


@pytest.fixture(autouse=True)
def context(monkeypatch):
    with patch("agent_builder_sdk.env_var.retrieve_auth_token"):
        monkeypatch.setenv("JOB_ID", "job-id")
        monkeypatch.setenv("WORKSPACE_ID", "workspace-id")
        monkeypatch.setenv("AGENT_INSTANCE_ID", "agent-instance-id")
        yield


@pytest.fixture
def mock_convert():
    with patch(
        "agent_builder_sdk.messages.message_handler.convert_queue_response_to_send_message_output",
        autospec=True,
    ) as mock:
        yield mock


@pytest.fixture
def handler(mock_queue_service):
    return MessageHandler(mock_queue_service)


async def test_send_message_no_queue():
    """Test MessageHandler validation when neither queue nor agent provided."""
    with pytest.raises(
        ValueError, match="Must provide either queue or agent for message processing"
    ):
        MessageHandler(None, None)


@pytest.mark.parametrize("a2a_message", ["sender-123"], indirect=["a2a_message"])
async def test_send_message_success(mock_convert, handler, a2a_message):
    """Test successful message processing."""
    mock_response = QueueResponse(
        request_id="request-123", context_id=a2a_message.contextId, message="Agent response"
    )
    handler.queue.wait_for_response.return_value = mock_response

    result = await handler.send_message(InvocationRequest(a2a_message))

    handler.queue.submit_request.assert_called_once_with(
        message=json.dumps([{"text": "Test message", "type": "text"}]),
        user_id=None,
        sender="sender-123",
        context_id=a2a_message.contextId,
        priority=RequestPriority.NORMAL,
        agent_instance_id="sender-123",
        task_id="task-789",
    )
    handler.queue.wait_for_response.assert_called_once_with(
        request_id="request-123",
        timeout=28,
        poll_interval=0.1,
    )
    assert result == mock_convert.return_value


@pytest.mark.parametrize("a2a_message", ["sender-123"], indirect=["a2a_message"])
async def test_send_message_timeout(mock_convert, handler, a2a_message):
    """Test message timeout."""
    handler.queue.wait_for_response.return_value = None  # Timeout

    with patch.object(handler, "_handle_delayed_response") as mock_delayed:
        result = await handler.send_message(InvocationRequest(a2a_message))

        # Should create delayed response task
        mock_delayed.assert_called_once_with("request-123", "sender-123", a2a_message)
        assert result == mock_convert.return_value


async def test_send_message_timeout_without_sender(mock_convert, handler, a2a_message):
    """Test message timeout without a sender does not send a delayed response."""
    handler.queue.wait_for_response.return_value = None  # Timeout
    a2a_message.metadata = None
    a2a_message.extensions = None

    with patch.object(handler, "_handle_delayed_response") as mock_delayed:
        result = await handler.send_message(InvocationRequest(a2a_message))

        mock_delayed.assert_not_called()
        assert result == mock_convert.return_value


async def test_send_message_exception(mock_convert, handler, a2a_message):
    """Test exception handling in send_message."""
    handler.queue.submit_request.side_effect = Exception("Queue error")

    result = await handler.send_message(InvocationRequest(a2a_message))

    assert result == mock_convert.return_value
    # Should call convert with error response using 'unknown' request_id
    mock_convert.assert_called_once()
    call_args = mock_convert.call_args[0]
    queue_response = call_args[0]
    assert queue_response.request_id == "unknown"
    assert queue_response.context_id == a2a_message.contextId
    assert "Failed to process message: Queue error" in queue_response.error_message


@patch("agent_builder_sdk.messages.message_handler.get_agent_context_from_env", autospec=True)
@patch("agent_builder_sdk.messages.message_handler.get_agentic_api_client", autospec=True)
async def test_handle_delayed_response_success(mock_client, _, handler, a2a_message):
    """Test successful delayed response handling."""
    mock_response = QueueResponse(
        request_id="request-123", context_id=a2a_message.contextId, message="Delayed response"
    )
    handler.queue.wait_for_response.return_value = mock_response

    await handler._handle_delayed_response("request-123", "sender-123", a2a_message)

    handler.queue.wait_for_response.assert_called_once_with(
        request_id="request-123", timeout=300, poll_interval=1
    )
    mock_client().send_message.assert_called_once()

    # Verify the parameters passed to send_message
    call_kwargs = mock_client().send_message.call_args[1]
    assert call_kwargs["agentInstanceId"] == "sender-123"
    assert "params" in call_kwargs
    assert "requestContext" in call_kwargs


@patch("agent_builder_sdk.messages.message_handler.get_agent_context_from_env", autospec=True)
@patch("agent_builder_sdk.messages.message_handler.get_agentic_api_client", autospec=True)
async def test_handle_delayed_response_timeout(mock_client, _, handler, a2a_message):
    """Test delayed response timeout."""
    handler.queue.wait_for_response.return_value = None  # Timeout

    await handler._handle_delayed_response("request-123", "sender-123", a2a_message)

    # Should still send timeout message
    mock_client().send_message.assert_called_once()


async def test_handle_delayed_response_no_queue(handler, a2a_message):
    """Test delayed response when queue is None."""
    handler.queue = None

    # Should not raise exception
    await handler._handle_delayed_response("request-123", "sender-123", a2a_message)


async def test_handle_delayed_response_exception(handler, a2a_message):
    """Test exception handling in delayed response."""
    handler.queue.wait_for_response.side_effect = Exception("Queue error")

    # Should not raise exception
    await handler._handle_delayed_response("request-123", "sender-123", a2a_message)


def test_handler_initialization(mock_queue_service):
    """Test MessageHandler initialization."""
    extensions = [Mock()]
    handler = MessageHandler(
        mock_queue_service, timeout=30, delayed_timeout=600, extension_handlers=extensions
    )

    assert handler.queue == mock_queue_service
    assert handler._timeout == 30
    assert handler._delayed_timeout == 600
    assert handler.extension_handlers == extensions


def test_handler_default_timeouts(handler):
    """Test MessageHandler default timeout values."""
    assert handler._timeout == 28
    assert handler._delayed_timeout == 300
    assert handler.extension_handlers is None


def test_handler_validation_both_provided(mock_queue_service):
    """Test MessageHandler validation when both queue and agent provided."""
    with pytest.raises(
        ValueError, match="Cannot provide both queue and agent - specify only one processing mode"
    ):
        MessageHandler(queue=mock_queue_service, agent=Mock())


def test_handler_validation_neither_provided():
    """Test MessageHandler validation when neither queue nor agent provided."""
    with pytest.raises(
        ValueError, match="Must provide either queue or agent for message processing"
    ):
        MessageHandler()


@pytest.mark.parametrize(
    "agent_class,process_method",
    [
        (BaseAgent, "process_message"),
        (AsyncBaseAgent, "process_message_async"),
    ],
)
async def test_send_message_with_agent(a2a_message, agent_result, agent_class, process_method):
    mock_agent = create_autospec(agent_class, spec_set=True, instance=True)
    getattr(mock_agent, process_method).return_value = agent_result
    handler = MessageHandler(agent=mock_agent)

    response = await handler.send_message(InvocationRequest(a2a_message))

    assert response.error is None
    assert response.result is not None
    assert response.result.parts == [{"text": "test agent result", "kind": "text"}]


async def test_send_message_with_acknowledgment_extension(mock_convert, handler, a2a_message):
    """Test message processing with acknowledgment extension."""
    mock_ack_handler = create_autospec(AcknowledgmentHandler(), spec_set=True, instance=True)
    mock_ack_handler.uri = "test://ack"
    mock_ack_handler.should_process.return_value = True
    mock_ack_response = QueueResponse(
        request_id="request-123",
        context_id=a2a_message.contextId,
        message="Working on it",
        metadata={"test://ack": True},
    )
    mock_ack_handler.process_request.return_value = mock_ack_response

    a2a_message.extensions.append("test://ack")
    handler.extension_handlers = [mock_ack_handler]

    with patch.object(handler, "_handle_delayed_response") as mock_delayed:
        result = await handler.send_message(InvocationRequest(a2a_message))

        mock_ack_handler.should_process.assert_called_once()
        mock_ack_handler.process_request.assert_called_once()
        mock_delayed.assert_called_once()
        assert result == mock_convert.return_value


async def test_send_message_with_acknowledgment_extension_no_ack(
    mock_convert, handler, a2a_message
):
    """Test message processing with acknowledgment extension that doesn't acknowledge."""
    mock_ack_handler = create_autospec(AcknowledgmentHandler(), spec_set=True, instance=True)
    mock_ack_handler.uri = "test://ack"
    mock_ack_handler.should_process.return_value = False

    a2a_message.extensions.append("test://ack")
    handler.extension_handlers = [mock_ack_handler]
    queue_response = QueueResponse("request-123", a2a_message.contextId, "Response")
    handler.queue.wait_for_response.return_value = queue_response

    result = await handler.send_message(InvocationRequest(a2a_message))

    mock_ack_handler.should_process.assert_called_once()
    mock_ack_handler.process_request.assert_not_called()
    handler.queue.wait_for_response.assert_called_once()
    assert result == mock_convert.return_value


# Task-related tests


class MockTaskStore:
    """Mock TaskStore for testing."""

    def __init__(self):
        self.tasks = {}

    async def store_task(self, task):
        self.tasks[task.id] = task

    async def get_task(self, task_id):
        return self.tasks.get(task_id)

    async def update_task(self, task):
        self.tasks[task.id] = task

    async def delete_task(self, task_id):
        self.tasks.pop(task_id, None)


class MockTaskManager:
    """Mock TaskManager for testing."""

    def __init__(self, task_store, should_create: bool = False):
        self.task_store = task_store
        self.should_create = should_create
        self.should_process = False
        self.should_create_task_called = False
        self.on_send_task_called = False
        self.on_receive_task_called = False

    async def should_create_task(self, request: InvocationRequest) -> bool:
        self.should_create_task_called = True
        return self.should_create

    async def should_process_task(self, request: InvocationRequest) -> bool:
        return self.should_process

    async def on_send_task(self, task, request):
        self.on_send_task_called = True
        await self.task_store.store_task(task)

    async def on_receive_task(self, task, request):
        self.on_receive_task_called = True
        await self.task_store.store_task(task)

    def get_task_creation_message(self, request):
        import uuid

        from agent_builder_sdk.custom_types.common_types import A2AMessage

        return A2AMessage(
            role="agent",
            parts=[{"text": "I'm working on your request...", "kind": "text"}],
            messageId=str(uuid.uuid4()),
            kind="message",
            contextId=request.message.contextId,
        )

    def get_task_process_message(self, request):
        import uuid

        from agent_builder_sdk.custom_types.common_types import A2AMessage

        return A2AMessage(
            role="agent",
            parts=[{"text": "I'm working on your request...", "kind": "text"}],
            messageId=str(uuid.uuid4()),
            kind="message",
            contextId=request.message.contextId,
        )


@pytest.fixture
def sample_task_request():
    """Create a sample InvocationRequest for task tests."""
    from agent_builder_sdk.custom_types.common_types import A2AMessage

    return InvocationRequest(
        message=A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test message"}],
            messageId="msg-123",
            kind="message",
        )
    )


@pytest.mark.asyncio
async def test_should_create_task_no_task_manager(sample_task_request):
    """Test _should_create_task returns False when no TaskManager."""
    agent = Mock()
    handler = MessageHandler(agent=agent)

    result = await handler._should_create_task(sample_task_request)

    assert result is False


@pytest.mark.asyncio
async def test_should_create_task_with_task_manager_false(sample_task_request):
    """Test _should_create_task delegates to TaskManager and returns False."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_create_task(sample_task_request)

    assert result is False
    assert task_manager.should_create_task_called


@pytest.mark.asyncio
async def test_should_create_task_with_task_manager_true(sample_task_request):
    """Test _should_create_task delegates to TaskManager and returns True."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=True)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_create_task(sample_task_request)

    assert result is True
    assert task_manager.should_create_task_called


@pytest.mark.asyncio
async def test_create_task_success(sample_task_request):
    """Test _create_task creates task with acknowledgment from TaskManager."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=True)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._create_task(sample_task_request)

    assert result.result is not None
    assert result.error is None
    assert hasattr(result.result, "id")
    assert hasattr(result.result, "status")
    assert result.result.status.message.role == "agent"
    assert "working on your request" in result.result.status.message.parts[0]["text"]
    assert task_manager.on_send_task_called


@pytest.mark.asyncio
async def test_create_task_no_task_manager(sample_task_request):
    """Test _create_task returns error when TaskManager not configured."""
    agent = Mock()
    handler = MessageHandler(agent=agent)

    result = await handler._create_task(sample_task_request)

    assert result.result is None
    assert result.error is not None
    assert result.error.message == "Task management not enabled"


@pytest.mark.asyncio
async def test_create_task_custom_acknowledgment(sample_task_request):
    """Test _create_task uses custom acknowledgment from TaskManager."""
    from agent_builder_sdk.custom_types.common_types import A2AMessage

    agent = Mock()
    task_store = MockTaskStore()

    class CustomAckTaskManager(MockTaskManager):
        def get_task_creation_message(self, request):
            return A2AMessage(
                role="agent",
                parts=[{"text": "Custom acknowledgment message", "kind": "text"}],
                messageId="custom-msg",
                kind="message",
                contextId=request.message.contextId,
            )

    task_manager = CustomAckTaskManager(task_store, should_create=True)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._create_task(sample_task_request)

    assert result.result.status.message.parts[0]["text"] == "Custom acknowledgment message"


@pytest.mark.asyncio
async def test_should_create_task_with_task_manager(sample_task_request):
    """Test _should_create_task returns True when TaskManager says so."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=True)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_create_task(sample_task_request)
    assert result is True


@pytest.mark.asyncio
async def test_should_create_task_without_task_manager(sample_task_request):
    """Test _should_create_task returns False when no TaskManager."""
    agent = Mock()
    handler = MessageHandler(agent=agent)

    result = await handler._should_create_task(sample_task_request)
    assert result is False


@pytest.mark.asyncio
async def test_should_create_task_manager_says_no(sample_task_request):
    """Test _should_create_task returns False when TaskManager says no."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_create_task(sample_task_request)
    assert result is False


@pytest.mark.asyncio
async def test_should_process_task_no_task_manager(sample_task_request):
    """Test _should_process_task returns False when no TaskManager."""
    agent = Mock()
    handler = MessageHandler(agent=agent)

    result = await handler._should_process_task(sample_task_request)

    assert result is False


@pytest.mark.asyncio
async def test_should_process_task_with_task_manager_false(sample_task_request):
    """Test _should_process_task delegates to TaskManager and returns False."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    task_manager.should_process = False
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_process_task(sample_task_request)

    assert result is False


@pytest.mark.asyncio
async def test_should_process_task_with_task_manager_true(sample_task_request):
    """Test _should_process_task delegates to TaskManager and returns True."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    task_manager.should_process = True
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._should_process_task(sample_task_request)

    assert result is True


@pytest.mark.asyncio
async def test_process_task_success(sample_task_request):
    """Test _process_task creates task and calls on_receive_task."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    task_manager.on_receive_task_called = False
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler._process_task(sample_task_request)

    assert result.result is not None
    assert result.error is None
    assert hasattr(result.result, "id")
    assert hasattr(result.result, "status")
    assert result.result.status.message.role == "agent"
    assert "working on your request" in result.result.status.message.parts[0]["text"]
    assert task_manager.on_receive_task_called


@pytest.mark.asyncio
async def test_process_task_no_task_manager(sample_task_request):
    """Test _process_task returns error when TaskManager not configured."""
    agent = Mock()
    handler = MessageHandler(agent=agent)

    result = await handler._process_task(sample_task_request)

    assert result.result is None
    assert result.error is not None
    assert result.error.message == "Task management not enabled"


@pytest.mark.asyncio
async def test_send_message_process_task_flow(sample_task_request):
    """Test send_message calls _process_task when should_process_task returns True."""
    agent = Mock()
    task_store = MockTaskStore()
    task_manager = MockTaskManager(task_store, should_create=False)
    task_manager.should_process = True
    handler = MessageHandler(agent=agent, task_manager=task_manager)

    result = await handler.send_message(sample_task_request)

    assert result.result is not None
    assert result.error is None
    assert task_manager.on_receive_task_called
    assert not task_manager.on_send_task_called  # Should not call on_send_task
