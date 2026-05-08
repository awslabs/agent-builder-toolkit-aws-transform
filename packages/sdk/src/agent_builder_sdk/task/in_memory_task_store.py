# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""In-memory task storage implementation."""

import logging
from typing import Dict, Optional

from agent_builder_sdk.custom_types.task_types import A2ATask

from .task_store import TaskStore

logger = logging.getLogger(__name__)


class InMemoryTaskStore(TaskStore):
    """
    In-memory task storage using a dictionary.

    Fast and simple storage suitable for:
    - Testing and development
    - Single-instance deployments
    - Short-lived tasks that don't need persistence

    Note: All tasks are lost when the process restarts.
    """

    def __init__(self):
        """Initialize the in-memory task store."""
        self._tasks: Dict[str, A2ATask] = {}
        logger.info("Initialized InMemoryTaskStore")

    async def store_task(self, task: A2ATask) -> None:
        """Store a new task in memory."""
        if task.id in self._tasks:
            raise ValueError(f"Task with ID {task.id} already exists")

        self._tasks[task.id] = task
        logger.debug(f"Stored task {task.id}")

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Retrieve a task from memory."""
        task = self._tasks.get(task_id)
        if task:
            logger.debug(f"Retrieved task {task_id}")
        else:
            logger.debug(f"Task {task_id} not found")
        return task

    async def update_task(self, task: A2ATask) -> None:
        """Update an existing task in memory."""
        if task.id not in self._tasks:
            raise ValueError(f"Task with ID {task.id} does not exist")

        self._tasks[task.id] = task
        logger.debug(f"Updated task {task.id}")
