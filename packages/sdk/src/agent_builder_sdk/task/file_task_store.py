# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""File-based task storage implementation."""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus

from ..custom_types.common_types import A2AMessage
from .task_store import TaskStore

logger = logging.getLogger(__name__)


class FileTaskStore(TaskStore):
    """
    File-based task storage using JSON files.

    Persistent storage suitable for:
    - Single-instance deployments needing persistence across restarts
    - Development and testing with state preservation
    - Checkpointing task state for recovery

    Each task is stored as a separate JSON file named {task_id}.json
    in the configured storage directory.

    For checkpointing: Use the same storage_dir as AgentRuntimeServer
    to ensure tasks are included in checkpoint artifacts and restored
    on agent restart or failover.
    """

    def __init__(self, storage_dir: str):
        """
        Initialize the file-based task store.

        Args:
            storage_dir: Directory path where task files will be stored
        """
        self.storage_dir = Path(storage_dir) / "tasks"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized FileTaskStore at {self.storage_dir}")

    def _get_task_path(self, task_id: str) -> Path:
        """Get the file path for a task ID."""
        return self.storage_dir / f"{task_id}.json"

    async def store_task(self, task: A2ATask) -> None:
        """Store a new task as a JSON file."""
        task_path = self._get_task_path(task.id)

        if task_path.exists():
            raise ValueError(f"Task with ID {task.id} already exists")

        try:
            self._write_task(task_path, task)
            logger.debug(f"Stored task {task.id} to {task_path}")
        except Exception as e:
            logger.error(f"Failed to store task {task.id}: {e}")
            raise

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Retrieve a task from a JSON file."""
        task_path = self._get_task_path(task_id)

        if not task_path.exists():
            logger.debug(f"Task {task_id} not found")
            return None

        try:
            with open(task_path, "r") as f:
                data = json.load(f)

            # Reconstruct A2ATask from dict
            task = self._dict_to_task(data)
            logger.debug(f"Retrieved task {task_id} from {task_path}")
            return task
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id}: {e}")
            raise

    async def update_task(self, task: A2ATask) -> None:
        """Update an existing task JSON file."""
        task_path = self._get_task_path(task.id)

        if not task_path.exists():
            raise ValueError(f"Task with ID {task.id} does not exist")

        try:
            self._write_task(task_path, task)
            logger.debug(f"Updated task {task.id} at {task_path}")
        except Exception as e:
            logger.error(f"Failed to update task {task.id}: {e}")
            raise

    async def list_tasks(self) -> List[A2ATask]:
        """List every task file in the storage directory, ordered by task ID.

        The files are read in a worker thread, so a large store does not block the
        event loop. A file that cannot be read or parsed as a task is skipped with a
        warning and the other tasks are still returned; ``get_task`` raises for it.
        """
        return await asyncio.to_thread(self._read_all_tasks)

    def _read_all_tasks(self) -> List[A2ATask]:
        """Load every readable task file, ordered by the task ID in the file name."""
        tasks: List[A2ATask] = []
        for task_path in sorted(self.storage_dir.glob("*.json"), key=lambda path: path.stem):
            try:
                with open(task_path, "r") as f:
                    tasks.append(self._dict_to_task(json.load(f)))
            except Exception as e:
                logger.warning(f"Skipping unreadable task file {task_path}: {e!r}")
        return tasks

    def _write_task(self, task_path: Path, task: A2ATask) -> None:
        """Write the task file through a temporary file and an atomic rename.

        A reader in another thread or process sees the previous file or the new one,
        never a partial write, and a failed write leaves the previous file in place.
        """
        tmp_path = task_path.with_name(f"{task_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(task.to_dict(), f, indent=2)
            os.replace(tmp_path, task_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _dict_to_task(self, data: dict) -> A2ATask:
        """Convert dictionary to A2ATask object."""
        # Reconstruct TaskStatus
        status_data = data["status"]
        status_message = None
        if status_data.get("message"):
            status_message = A2AMessage(**status_data["message"])

        status = TaskStatus(
            state=TaskState(status_data["state"]),
            message=status_message,
            timestamp=status_data.get("timestamp"),
        )

        # Reconstruct history messages
        history = None
        if data.get("history"):
            history = [A2AMessage(**msg) for msg in data["history"]]

        # Reconstruct A2ATask
        return A2ATask(
            id=data["id"],
            contextId=data["contextId"],
            status=status,
            history=history,
            artifacts=data.get("artifacts"),
            metadata=data.get("metadata"),
        )
