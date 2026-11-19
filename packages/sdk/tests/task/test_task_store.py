# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TaskStore implementations."""

import asyncio
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import IO, Any, List, Optional

import pytest

from agent_builder_sdk.custom_types.common_types import A2AMessage
from agent_builder_sdk.custom_types.task_types import (
    TERMINAL_TASK_STATES,
    A2ATask,
    TaskState,
    TaskStatus,
)
from agent_builder_sdk.task.file_task_store import FileTaskStore
from agent_builder_sdk.task.in_memory_task_store import InMemoryTaskStore
from agent_builder_sdk.task.task_store import TaskStore


def make_task(task_id: str, state: TaskState = TaskState.SUBMITTED) -> A2ATask:
    """Create a minimal task with the given ID and state."""
    return A2ATask(id=task_id, contextId="ctx-456", status=TaskStatus(state=state))


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

    @pytest.mark.asyncio
    async def test_list_tasks_empty_store_returns_empty_list(self) -> None:
        """An empty store lists no tasks and does not raise."""
        assert await InMemoryTaskStore().list_tasks() == []

    @pytest.mark.asyncio
    async def test_list_tasks_orders_by_task_id(self) -> None:
        """Tasks come back ordered by ID, not by insertion."""
        store = InMemoryTaskStore()
        for task_id in ("task-b", "task-c", "task-a"):
            await store.store_task(make_task(task_id))

        assert [task.id for task in await store.list_tasks()] == ["task-a", "task-b", "task-c"]

    @pytest.mark.asyncio
    async def test_terminal_task_states_select_unfinished_tasks(self) -> None:
        """Filtering a listing on TERMINAL_TASK_STATES leaves the tasks that can still change."""
        store = InMemoryTaskStore()
        for state in TaskState:
            await store.store_task(make_task(state.value, state))

        unfinished = [
            task.id
            for task in await store.list_tasks()
            if task.status.state not in TERMINAL_TASK_STATES
        ]
        assert unfinished == ["auth-required", "input-required", "submitted", "unknown", "working"]


class TestTaskStoreListDefault:
    """Tests for the list_tasks default on the TaskStore interface."""

    @pytest.mark.asyncio
    async def test_store_without_list_tasks_instantiates_and_raises_on_call(self) -> None:
        """A store with only the abstract methods stays valid; list_tasks says it is missing."""

        class MinimalStore(TaskStore):
            async def store_task(self, task: A2ATask) -> None:
                pass

            async def get_task(self, task_id: str) -> Optional[A2ATask]:
                return None

            async def update_task(self, task: A2ATask) -> None:
                pass

        with pytest.raises(NotImplementedError, match="MinimalStore does not implement"):
            await MinimalStore().list_tasks()


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

    @pytest.mark.asyncio
    async def test_failed_update_keeps_previous_task_file(
        self, sample_task: A2ATask, temp_storage_dir: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A write that fails part-way leaves the stored task readable and no stray file."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(sample_task)

        def write_half_then_fail(obj: Any, fp: IO[str], **kwargs: Any) -> None:
            fp.write('{"id": ')
            raise OSError("disk full")

        monkeypatch.setattr(json, "dump", write_half_then_fail)
        sample_task.status.state = TaskState.COMPLETED
        with pytest.raises(OSError, match="disk full"):
            await store.update_task(sample_task)

        retrieved = await store.get_task(sample_task.id)
        assert retrieved is not None
        assert retrieved.status.state == TaskState.SUBMITTED
        assert os.listdir(store.storage_dir) == [f"{sample_task.id}.json"]

    @pytest.mark.asyncio
    async def test_list_tasks_empty_store_returns_empty_list(self, temp_storage_dir: str) -> None:
        """A store with no task file lists no tasks and does not raise."""
        assert await FileTaskStore(storage_dir=temp_storage_dir).list_tasks() == []

    @pytest.mark.asyncio
    async def test_list_tasks_orders_by_task_id_across_instances(
        self, sample_task: A2ATask, temp_storage_dir: str
    ) -> None:
        """A new store on the same directory lists the persisted tasks ordered by ID."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        # "task-1-retry.json" sorts before "task-1.json" as a file name, after it as an ID.
        # The file of the empty ID is ".json": its stem is ".json", after ".hidden".
        for task_id in ("task-1-retry", ".hidden", "task-1", ""):
            await store.store_task(make_task(task_id))
        await store.store_task(sample_task)
        # A complete temporary file, as a writer stopped before its rename leaves behind.
        leftover = store.storage_dir / ".deadbeef.tmp"
        leftover.write_text(json.dumps(make_task("task-1", TaskState.WORKING).to_dict()))

        tasks = await FileTaskStore(storage_dir=temp_storage_dir).list_tasks()

        assert [task.id for task in tasks] == [
            "",
            ".hidden",
            "task-1",
            "task-1-retry",
            sample_task.id,
        ]
        assert tasks[2].status.state == TaskState.SUBMITTED
        assert tasks[4].to_dict() == sample_task.to_dict()

    @pytest.mark.asyncio
    async def test_list_tasks_reads_files_in_worker_thread(
        self, temp_storage_dir: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The file reads run off the event loop thread."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(make_task("task-a"))
        read_all_tasks = store._read_all_tasks
        reader_threads: List[int] = []

        def record_thread() -> List[A2ATask]:
            reader_threads.append(threading.get_ident())
            return read_all_tasks()

        monkeypatch.setattr(store, "_read_all_tasks", record_thread)
        tasks = await store.list_tasks()

        assert [task.id for task in tasks] == ["task-a"]
        assert len(reader_threads) == 1
        assert reader_threads[0] != threading.get_ident()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("content", "cause"),
        [
            ('{"id": "broken", "contextId"', "JSONDecodeError"),
            ("[]", "TypeError"),
            ('{"id": "broken"}', "KeyError"),
            ("", "JSONDecodeError"),
        ],
        ids=["truncated", "not-an-object", "missing-fields", "empty"],
    )
    async def test_list_tasks_skips_unreadable_file_with_warning(
        self, content: str, cause: str, temp_storage_dir: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One bad task file is skipped with a warning that names the file and the cause."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        await store.store_task(make_task("task-a"))
        await store.store_task(make_task("task-c"))
        (store.storage_dir / "broken.json").write_text(content)

        with caplog.at_level(logging.WARNING, logger="agent_builder_sdk.task.file_task_store"):
            tasks = await store.list_tasks()

        assert [task.id for task in tasks] == ["task-a", "task-c"]
        warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
        assert len(warnings) == 1
        assert "broken.json" in warnings[0].getMessage()
        assert cause in warnings[0].getMessage()

    @pytest.mark.asyncio
    async def test_update_during_listing_renames_after_directory_scan(
        self, temp_storage_dir: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An update that arrives while list_tasks scans the directory renames after the scan."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        task = make_task("task-a")
        await store.store_task(task)
        scan_started = threading.Event()
        renamed = threading.Event()
        renamed_during_scan: List[bool] = []
        real_glob = Path.glob
        real_replace = os.replace

        def scan_then_wait_for_rename(self: Path, pattern: str) -> List[Path]:
            paths = list(real_glob(self, pattern))
            scan_started.set()
            renamed_during_scan.append(renamed.wait(timeout=0.2))
            return paths

        def replace_and_signal(src: Path, dst: Path) -> None:
            real_replace(src, dst)
            renamed.set()

        monkeypatch.setattr(Path, "glob", scan_then_wait_for_rename)
        monkeypatch.setattr(os, "replace", replace_and_signal)
        listing = asyncio.create_task(store.list_tasks())
        assert await asyncio.to_thread(scan_started.wait, 5)
        task.status.state = TaskState.COMPLETED
        await store.update_task(task)

        assert [listed.id for listed in await listing] == ["task-a"]
        assert renamed_during_scan == [False]
        assert renamed.is_set()

    @pytest.mark.asyncio
    async def test_task_id_at_file_name_length_limit_stores_and_updates(
        self, temp_storage_dir: str
    ) -> None:
        """A 250-character ID, whose file name is at the 255-byte limit, stores and updates."""
        store = FileTaskStore(storage_dir=temp_storage_dir)
        task = make_task("x" * 250)
        await store.store_task(task)
        task.status.state = TaskState.COMPLETED
        await store.update_task(task)

        assert [listed.status.state for listed in await store.list_tasks()] == [TaskState.COMPLETED]
