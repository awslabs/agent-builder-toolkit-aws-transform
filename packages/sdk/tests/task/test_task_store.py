"""Unit tests for TaskStore implementations."""

import os
import tempfile
from pathlib import Path

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus
from agent_builder_sdk.task.file_task_store import FileTaskStore
from agent_builder_sdk.task.in_memory_task_store import InMemoryTaskStore


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
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
        history=[
            A2AMessage(
                role="agent",
                parts=[{"kind": "text", "text": "Task created"}],
                messageId="msg-0",
                kind="message",
                contextId="ctx-456",
            )
        ],
    )


class TestInMemoryTaskStore:
    """Tests for InMemoryTaskStore."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_task(self, sample_task):
        """Test storing and retrieving a task."""
        store = InMemoryTaskStore()
        await store.store_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert retrieved is not None
        assert retrieved.id == sample_task.id
        assert retrieved.contextId == sample_task.contextId
        assert retrieved.status.state == TaskState.SUBMITTED

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self):
        """Test retrieving a task that doesn't exist."""
        store = InMemoryTaskStore()
        result = await store.get_task("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task(self, sample_task):
        """Test updating an existing task."""
        store = InMemoryTaskStore()
        await store.store_task(sample_task)

        # Update task status
        sample_task.status.state = TaskState.WORKING
        sample_task.status.message.parts[0]["text"] = "Task in progress"
        await store.update_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert retrieved.status.state == TaskState.WORKING
        assert retrieved.status.message.parts[0]["text"] == "Task in progress"

    @pytest.mark.asyncio
    async def test_history_accumulation(self, sample_task):
        """Test that task history accumulates correctly."""
        store = InMemoryTaskStore()
        await store.store_task(sample_task)

        # Add new status to history
        new_message = A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": "Processing"}],
            messageId="msg-2",
            kind="message",
            contextId="ctx-456",
        )
        sample_task.history.append(new_message)
        await store.update_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert len(retrieved.history) == 2
        assert retrieved.history[1].parts[0]["text"] == "Processing"

    @pytest.mark.asyncio
    async def test_store_task_duplicate_raises(self, sample_task):
        """Test storing duplicate task raises ValueError."""
        store = InMemoryTaskStore()
        await store.store_task(sample_task)

        with pytest.raises(ValueError, match="already exists"):
            await store.store_task(sample_task)

    @pytest.mark.asyncio
    async def test_update_task_not_found_raises(self, sample_task):
        """Test updating non-existent task raises ValueError."""
        store = InMemoryTaskStore()

        with pytest.raises(ValueError, match="does not exist"):
            await store.update_task(sample_task)

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        """Test getting non-existent task returns None."""
        store = InMemoryTaskStore()
        result = await store.get_task("nonexistent")
        assert result is None


class TestFileTaskStore:
    """Tests for FileTaskStore."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for file storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_upsert_and_get_task(self, sample_task, temp_storage_dir):
        """Test storing and retrieving a task from file."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        # Verify file was created in tasks subfolder
        task_file = Path(temp_storage_dir) / "tasks" / f"{sample_task.id}.json"
        assert task_file.exists()

        retrieved = await store.get_task(sample_task.id)
        assert retrieved is not None
        assert retrieved.id == sample_task.id
        assert retrieved.contextId == sample_task.contextId
        assert retrieved.status.state == TaskState.SUBMITTED

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, temp_storage_dir):
        """Test retrieving a task that doesn't exist."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        result = await store.get_task("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task(self, sample_task, temp_storage_dir):
        """Test updating an existing task in file."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        # Update task status
        sample_task.status.state = TaskState.COMPLETED
        sample_task.status.message.parts[0]["text"] = "Task completed"
        await store.update_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert retrieved.status.state == TaskState.COMPLETED
        assert retrieved.status.message.parts[0]["text"] == "Task completed"

    @pytest.mark.asyncio
    async def test_message_reconstruction(self, sample_task, temp_storage_dir):
        """Test that A2AMessage objects are properly reconstructed from JSON."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        retrieved = await store.get_task(sample_task.id)

        # Verify status message is A2AMessage instance
        assert isinstance(retrieved.status.message, A2AMessage)
        assert retrieved.status.message.role == "agent"
        assert retrieved.status.message.contextId == "ctx-456"

        # Verify history messages are A2AMessage instances
        assert len(retrieved.history) == 1
        assert isinstance(retrieved.history[0], A2AMessage)
        assert retrieved.history[0].messageId == "msg-0"

    @pytest.mark.asyncio
    async def test_history_accumulation(self, sample_task, temp_storage_dir):
        """Test that task history accumulates correctly in file storage."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        # Add new status to history
        new_message = A2AMessage(
            role="agent",
            parts=[{"kind": "text", "text": "Working"}],
            messageId="msg-2",
            kind="message",
            contextId="ctx-456",
        )
        sample_task.history.append(new_message)
        await store.update_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert len(retrieved.history) == 2
        assert isinstance(retrieved.history[1], A2AMessage)
        assert retrieved.history[1].parts[0]["text"] == "Working"

    @pytest.mark.asyncio
    async def test_storage_directory_creation(self):
        """Test that storage directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "nested", "tasks")
            store = FileTaskStore(storage_dir=storage_path)

            task = A2ATask(
                id="test-123",
                contextId="ctx-123",
                status=TaskStatus(
                    state=TaskState.SUBMITTED,
                    message=A2AMessage(
                        role="agent",
                        parts=[{"kind": "text", "text": "Test"}],
                        messageId="msg-1",
                        kind="message",
                        contextId="ctx-123",
                    ),
                ),
            )

            await store.store_task(task)
            # FileTaskStore creates tasks subfolder, so check tasks/tasks/test-123.json
            assert (Path(storage_path) / "tasks" / "test-123.json").exists()

    @pytest.mark.asyncio
    async def test_store_task_duplicate_raises(self, sample_task, temp_storage_dir):
        """Test storing duplicate task raises ValueError."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        with pytest.raises(ValueError, match="already exists"):
            await store.store_task(sample_task)

    @pytest.mark.asyncio
    async def test_update_task_not_found_raises(self, sample_task, temp_storage_dir):
        """Test updating non-existent task raises ValueError."""
        store = FileTaskStore(storage_dir=temp_storage_dir)

        with pytest.raises(ValueError, match="does not exist"):
            await store.update_task(sample_task)

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, temp_storage_dir):
        """Test getting non-existent task returns None."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        result = await store.get_task("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_task_with_history(self, temp_storage_dir):
        """Test storing and retrieving task with history."""
        store = FileTaskStore(storage_dir=temp_storage_dir)

        task = A2ATask(
            id="task-with-history",
            contextId="ctx-123",
            status=TaskStatus(
                state=TaskState.COMPLETED,
                message=A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "Completed"}],
                    messageId="msg-final",
                    kind="message",
                    contextId="ctx-123",
                ),
            ),
            history=[
                A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "Started"}],
                    messageId="msg-1",
                    kind="message",
                    contextId="ctx-123",
                ),
                A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "In progress"}],
                    messageId="msg-2",
                    kind="message",
                    contextId="ctx-123",
                ),
            ],
        )

        await store.store_task(task)
        retrieved = await store.get_task(task.id)

        assert retrieved is not None
        assert len(retrieved.history) == 2
        assert retrieved.history[0].parts[0]["text"] == "Started"
        assert retrieved.history[1].parts[0]["text"] == "In progress"

    @pytest.mark.asyncio
    async def test_task_with_metadata(self, temp_storage_dir):
        """Test storing and retrieving task with metadata."""
        store = FileTaskStore(storage_dir=temp_storage_dir)

        task = A2ATask(
            id="task-with-metadata",
            contextId="ctx-123",
            status=TaskStatus(
                state=TaskState.WORKING,
                message=A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "Working"}],
                    messageId="msg-1",
                    kind="message",
                    contextId="ctx-123",
                ),
            ),
            metadata={"priority": "high", "tags": ["urgent", "customer"]},
        )

        await store.store_task(task)
        retrieved = await store.get_task(task.id)

        assert retrieved is not None
        assert retrieved.metadata == {"priority": "high", "tags": ["urgent", "customer"]}

    @pytest.mark.asyncio
    async def test_task_with_artifacts(self, temp_storage_dir):
        """Test storing and retrieving task with artifacts."""
        store = FileTaskStore(storage_dir=temp_storage_dir)

        task = A2ATask(
            id="task-with-artifacts",
            contextId="ctx-123",
            status=TaskStatus(
                state=TaskState.COMPLETED,
                message=A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "Done"}],
                    messageId="msg-1",
                    kind="message",
                    contextId="ctx-123",
                ),
            ),
            artifacts=["s3://bucket/result1.json", "s3://bucket/result2.json"],
        )

        await store.store_task(task)
        retrieved = await store.get_task(task.id)

        assert retrieved is not None
        assert retrieved.artifacts == ["s3://bucket/result1.json", "s3://bucket/result2.json"]
