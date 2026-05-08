# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TaskManager."""

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus
from agent_builder_sdk.task.in_memory_task_store import InMemoryTaskStore
from agent_builder_sdk.task.task_manager import TaskManager


class MockTaskManager(TaskManager):
    """Mock TaskManager for testing."""

    def __init__(self, task_store, should_create=True):
        super().__init__(task_store)
        self._should_create = should_create
        self.on_send_task_called = False
        self.sent_task = None

    async def should_create_task(self, request: InvocationRequest) -> bool:
        return self._should_create

    async def on_send_task(self, task: A2ATask, request: InvocationRequest) -> None:
        self.on_send_task_called = True
        self.sent_task = task
        await self.upsert_task(task)


@pytest.fixture
def task_store():
    """Create a task store for testing."""
    return InMemoryTaskStore()


@pytest.fixture
def sample_request():
    """Create a sample request for testing."""
    return InvocationRequest(
        message=A2AMessage(
            role="user",
            parts=[{"kind": "text", "text": "Test message"}],
            messageId="msg-123",
            kind="message",
            contextId="ctx-456",
        )
    )


class TestTaskManager:
    """Tests for TaskManager base class."""

    @pytest.mark.asyncio
    async def test_should_create_task(self, task_store, sample_request):
        """Test should_create_task returns configured value."""
        manager = MockTaskManager(task_store, should_create=True)
        assert await manager.should_create_task(sample_request) is True

        manager = MockTaskManager(task_store, should_create=False)
        assert await manager.should_create_task(sample_request) is False

    @pytest.mark.asyncio
    async def test_on_send_task(self, task_store, sample_request):
        """Test on_send_task is called with task."""
        manager = MockTaskManager(task_store)

        task = A2ATask(
            id="test-123",
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

        await manager.on_send_task(task, sample_request)

        assert manager.on_send_task_called is True
        assert manager.sent_task == task

    def test_get_task_creation_message_default(self, task_store, sample_request):
        """Test default task creation message."""
        manager = MockTaskManager(task_store)
        ack = manager.get_task_creation_message(sample_request)

        assert isinstance(ack, A2AMessage)
        assert ack.role == "agent"
        assert ack.kind == "message"
        assert ack.contextId == "ctx-456"
        assert "working on your request" in ack.parts[0]["text"].lower()

    def test_get_task_creation_message_custom(self, task_store, sample_request):
        """Test custom task creation message."""

        class CustomAckManager(MockTaskManager):
            def get_task_creation_message(self, request):
                return A2AMessage(
                    role="agent",
                    parts=[{"kind": "text", "text": "Custom message"}],
                    messageId="custom-msg",
                    kind="message",
                    contextId=request.message.contextId,
                )

        manager = CustomAckManager(task_store)
        ack = manager.get_task_creation_message(sample_request)

        assert ack.parts[0]["text"] == "Custom message"
        assert ack.messageId == "custom-msg"

    @pytest.mark.asyncio
    async def test_on_get_task(self, task_store):
        """Test on_get_task retrieves task from store."""
        manager = MockTaskManager(task_store)

        task = A2ATask(
            id="test-123",
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

        await manager.upsert_task(task)
        retrieved = await manager.on_get_task("test-123")

        assert retrieved is not None
        assert retrieved.id == "test-123"

    @pytest.mark.asyncio
    async def test_on_get_task_nonexistent(self, task_store):
        """Test on_get_task returns None for nonexistent task."""
        manager = MockTaskManager(task_store)
        result = await manager.on_get_task("nonexistent")
        assert result is None

    def test_supports_auto_upgrade_default(self, task_store):
        """Test supports_auto_upgrade returns False by default."""
        manager = MockTaskManager(task_store)
        assert manager.supports_auto_upgrade() is False

    def test_supports_auto_upgrade_custom(self, task_store):
        """Test custom supports_auto_upgrade implementation."""

        class AutoUpgradeManager(MockTaskManager):
            def supports_auto_upgrade(self):
                return True

        manager = AutoUpgradeManager(task_store)
        assert manager.supports_auto_upgrade() is True

    @pytest.mark.asyncio
    async def test_upsert_task(self, task_store):
        """Test upsert_task stores task in task_store."""
        manager = MockTaskManager(task_store)

        task = A2ATask(
            id="test-123",
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

        await manager.upsert_task(task)
        retrieved = await task_store.get_task("test-123")

        assert retrieved is not None
        assert retrieved.id == "test-123"

    @pytest.mark.asyncio
    async def test_update_task(self, task_store):
        """Test update_task updates task in task_store."""
        manager = MockTaskManager(task_store)

        task = A2ATask(
            id="test-123",
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

        await manager.upsert_task(task)

        # Update task
        task.status.state = TaskState.COMPLETED
        await manager.upsert_task(task)

        retrieved = await task_store.get_task("test-123")
        assert retrieved.status.state == TaskState.COMPLETED
