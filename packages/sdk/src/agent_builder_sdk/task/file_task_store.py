"""File-based task storage implementation."""

import json
import logging
from pathlib import Path
from typing import Optional

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
            with open(task_path, "w") as f:
                json.dump(task.to_dict(), f, indent=2)
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
            with open(task_path, "w") as f:
                json.dump(task.to_dict(), f, indent=2)
            logger.debug(f"Updated task {task.id} at {task_path}")
        except Exception as e:
            logger.error(f"Failed to update task {task.id}: {e}")
            raise

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
