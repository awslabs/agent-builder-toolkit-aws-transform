"""Tests for ExampleAlwaysCreateTaskManager."""

from unittest.mock import MagicMock

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus
from agent_builder_sdk.task.example_task_manager import ExampleAlwaysCreateTaskManager
from agent_builder_sdk.task.in_memory_task_store import InMemoryTaskStore


@pytest.fixture
def task_store():
    """Create an in-memory task store for testing."""
    return InMemoryTaskStore()


@pytest.fixture
def mock_queue():
    """Create a mock queue service."""
    return MagicMock()


@pytest.fixture
def manager(task_store, mock_queue):
    """Create an ExampleAlwaysCreateTaskManager instance."""
    return ExampleAlwaysCreateTaskManager(task_store, mock_queue)


@pytest.fixture
def sample_request():
    """Create a sample invocation request."""
    return InvocationRequest(
        message=A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test request"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )
    )


@pytest.fixture
def sample_task():
    """Create a sample task."""
    return A2ATask(
        id="test-task-123",
        contextId="ctx-456",
        status=TaskStatus(
            state=TaskState.SUBMITTED,
            message=A2AMessage(
                role="agent",
                parts=[{"kind": "text", "text": "Task submitted"}],
                messageId="msg-1",
                kind="message",
                contextId="ctx-456",
            ),
        ),
    )


class TestExampleAlwaysCreateTaskManager:
    """Tests for ExampleAlwaysCreateTaskManager."""

    @pytest.mark.asyncio
    async def test_should_create_task_always_true(self, manager, sample_request):
        """Test that should_create_task always returns True."""
        result = await manager.should_create_task(sample_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_on_send_task_stores_task(self, manager, task_store, sample_task, sample_request):
        """Test that on_send_task stores the task."""
        await manager.on_send_task(sample_task, sample_request)

        # Verify task was stored
        stored_task = await task_store.get_task(sample_task.id)
        assert stored_task is not None
        assert stored_task.id == sample_task.id

    @pytest.mark.asyncio
    async def test_on_send_task_starts_background_processing(
        self, manager, sample_task, sample_request
    ):
        """Test that on_send_task starts background processing."""
        # Just verify it doesn't raise an exception
        await manager.on_send_task(sample_task, sample_request)
        # Background task is created but we don't wait for it

    @pytest.mark.asyncio
    async def test_update_task_status(self, manager, task_store, sample_task):
        """Test _update_task_status updates task state."""
        await task_store.store_task(sample_task)

        await manager._update_task_status(sample_task.id, TaskState.WORKING, "Processing...")

        updated_task = await task_store.get_task(sample_task.id)
        assert updated_task.status.state == TaskState.WORKING
        assert updated_task.status.message.parts[0]["text"] == "Processing..."

    @pytest.mark.asyncio
    async def test_update_task_status_nonexistent_task(self, manager):
        """Test _update_task_status with nonexistent task doesn't raise."""
        # Should not raise exception
        await manager._update_task_status("nonexistent", TaskState.FAILED, "Error")

    @pytest.mark.asyncio
    async def test_process_task_updates_status_to_completed(
        self, task_store, sample_task, mock_queue, monkeypatch
    ):
        """Test that background processing eventually completes the task."""
        import asyncio

        # Mock asyncio.sleep to make test fast
        async def mock_sleep(seconds):
            pass

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        manager = ExampleAlwaysCreateTaskManager(task_store, mock_queue)
        await task_store.store_task(sample_task)

        # Run the background processing (now fast with mocked sleep)
        await manager._process_task_with_fast_updates(sample_task.id)

        # Verify task reached completed state
        final_task = await task_store.get_task(sample_task.id)
        assert final_task.status.state == TaskState.COMPLETED
        assert "completed successfully" in final_task.status.message.parts[0]["text"].lower()

    @pytest.mark.asyncio
    async def test_process_task_handles_exception(self, sample_task, mock_queue, monkeypatch):
        """Test that background processing handles exceptions gracefully."""
        import asyncio

        # Mock asyncio.sleep to make test fast
        async def mock_sleep(seconds):
            pass

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        class FailingTaskStore(InMemoryTaskStore):
            """Task store that fails on first update."""

            def __init__(self):
                super().__init__()
                self.update_count = 0

            async def update_task(self, task):
                self.update_count += 1
                if self.update_count == 1:
                    raise Exception("Test error")
                await super().update_task(task)

        failing_store = FailingTaskStore()
        manager = ExampleAlwaysCreateTaskManager(failing_store, mock_queue)

        await failing_store.store_task(sample_task)

        # Should handle exception and mark task as failed
        await manager._process_task_with_fast_updates(sample_task.id)

        final_task = await failing_store.get_task(sample_task.id)
        assert final_task.status.state == TaskState.FAILED
        assert "failed" in final_task.status.message.parts[0]["text"].lower()

    @pytest.mark.asyncio
    async def test_should_process_task_with_task_id(self, manager, sample_request):
        """Test that should_process_task returns True when taskId is present."""
        sample_request.message.taskId = "task-123"
        result = await manager.should_process_task(sample_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_process_task_without_task_id(self, manager, sample_request):
        """Test that should_process_task returns False when taskId is None."""
        sample_request.message.taskId = None
        result = await manager.should_process_task(sample_request)
        assert result is False

    @pytest.mark.asyncio
    async def test_on_receive_task_stores_task(
        self, manager, task_store, sample_task, sample_request
    ):
        """Test that on_receive_task stores the task and starts background processing."""
        await manager.on_receive_task(sample_task, sample_request)

        # Verify task was stored
        stored_task = await task_store.get_task(sample_task.id)
        assert stored_task is not None
        assert stored_task.id == sample_task.id
