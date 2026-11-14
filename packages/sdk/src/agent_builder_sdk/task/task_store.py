# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
TaskStore interface for task persistence.

Provides abstract storage interface that consumers can implement
with different backends (memory, file, database, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Optional

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

    async def list_tasks(self) -> List[A2ATask]:
        """List every stored task, ordered by task ID (ascending string order).

        Use it to find tasks without tracking their IDs elsewhere, for example to
        resume after a restart the tasks whose state is not in
        ``agent_builder_sdk.custom_types.task_types.TERMINAL_TASK_STATES``.

        Not abstract: a subclass that implements only the abstract methods stays
        valid. A store that supports listing overrides this method.

        Returns:
            All stored tasks, or an empty list when the store holds none

        Raises:
            NotImplementedError: If the store does not override this method
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement list_tasks")
