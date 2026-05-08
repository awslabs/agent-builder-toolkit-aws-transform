# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Example TaskManager implementation demonstrating task creation patterns."""

import asyncio
import logging
import uuid

from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.custom_types.task_types import A2ATask, TaskState, TaskStatus
from agent_builder_sdk.message_queue import QueueService

from .task_manager import TaskManager
from .task_store import TaskStore

logger = logging.getLogger(__name__)


class ExampleAlwaysCreateTaskManager(TaskManager):
    """
    Example TaskManager demonstrating always-create-task pattern.

    This is a reference implementation for testing - it does NOT invoke
    actual LLM models or perform real work. Instead, it simulates ~90 seconds
    of processing with periodic status updates.

    Key behaviors:
    - should_create_task(): Always returns True
    - Background processing: Mock updates every 15 seconds
    - Designed for testing with ATX_CHAT (3-minute timeout)

    For agent implementations, consumers can:
    - Add conditional logic in should_create_task() based on request analysis
    - Use queue for orchestrator pattern: await self.queue.submit_request(...)
    - Customize status update frequency and messaging
    """

    def __init__(self, task_store: TaskStore, queue: QueueService):
        """Initialize with dependencies from TaskManagerContext.

        Args:
            task_store: Storage backend for tasks
            queue: Queue service for background processing
        """
        super().__init__(task_store)
        self.queue = queue

    async def should_create_task(self, request: InvocationRequest) -> bool:
        """Always create tasks - useful for testing task flow."""
        return True

    async def on_send_task(self, task: A2ATask, request: InvocationRequest) -> None:
        """Store task and start background processing."""
        logger.info(f"Creating task {task.id} with background processing")
        await self.upsert_task(task)
        asyncio.create_task(self._process_task_with_fast_updates(task.id))

    async def should_process_task(self, request: InvocationRequest) -> bool:
        """Check if taskId is populated in the request"""
        return request.message.taskId is not None

    async def on_receive_task(self, task: A2ATask, request: InvocationRequest) -> None:
        """Store task and start background processing."""
        logger.info(f"Processing task {task.id} with background processing")
        await self.upsert_task(task)
        asyncio.create_task(self._process_task_with_fast_updates(task.id))

    async def _process_task_with_fast_updates(self, task_id: str) -> None:
        """Simulate background processing with periodic status updates."""
        try:
            await asyncio.sleep(30)  # Initial wait

            await self._update_task_status(
                task_id, TaskState.WORKING, "Starting task processing..."
            )
            await asyncio.sleep(15)

            await self._update_task_status(
                task_id, TaskState.WORKING, "Processing request - 30% complete"
            )
            await asyncio.sleep(15)

            await self._update_task_status(
                task_id, TaskState.WORKING, "Processing request - 60% complete"
            )
            await asyncio.sleep(15)

            await self._update_task_status(
                task_id, TaskState.WORKING, "Finalizing results - 90% complete"
            )
            await asyncio.sleep(15)

            await self._update_task_status(
                task_id, TaskState.COMPLETED, "Task completed successfully"
            )

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            await self._update_task_status(task_id, TaskState.FAILED, f"Task failed: {str(e)}")

    async def _update_task_status(self, task_id: str, state: TaskState, message: str) -> None:
        """Update task status - clients can poll via GetTask."""
        task = await self.task_store.get_task(task_id)
        if task:
            status_message = A2AMessage(
                role="agent",
                parts=[{"kind": "text", "text": message}],
                messageId=str(uuid.uuid4()),
                kind="message",
                contextId=task.contextId,
            )

            # Update current status
            task.status = TaskStatus(state=state, message=status_message)

            # Append to history for complete chronological record
            if task.history is None:
                task.history = []
            task.history.append(status_message)

            await self.task_store.update_task(task)
            logger.info(f"Task {task_id} updated: {state.value} - {message}")
