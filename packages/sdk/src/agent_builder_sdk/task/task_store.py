"""
TaskStore interface for task persistence.

Provides abstract storage interface that consumers can implement
with different backends (memory, file, database, etc.).
"""

from abc import ABC, abstractmethod
from typing import Optional

from agent_builder_sdk.custom_types.task_types import A2ATask
from agent_builder_sdk.util.decorators import experimental


@experimental("TaskStore is experimental and subject to breaking changes")
class TaskStore(ABC):
    """Abstract interface for task storage that consumers implement."""

    @abstractmethod
    async def store_task(self, task: A2ATask) -> None:
        """Store a new task.

        Args:
            task: Task to store

        Raises:
            Exception: If task already exists or storage fails
        """
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Retrieve a task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_task(self, task: A2ATask) -> None:
        """Update an existing task.

        Args:
            task: Task with updated information

        Raises:
            Exception: If task not found or update fails
        """
        pass
