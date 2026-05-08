# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
TaskManager interface for task creation and management.

Provides pluggable interface for consumers to implement task creation logic
and background processing.

Task creation patterns:
- should_create_task(): Upfront decision based on request analysis
- supports_auto_upgrade(): TODO - Auto-upgrade on timeout (not yet implemented)
"""

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from agent_builder_sdk.custom_types.common_types import A2AMessage, InvocationRequest
from agent_builder_sdk.custom_types.task_types import A2ATask
from agent_builder_sdk.task.task_store import TaskStore
from agent_builder_sdk.util.decorators import experimental


@experimental("TaskManager is experimental and subject to breaking changes")
class TaskManager(ABC):
    """Abstract interface for task management that consumers implement.

    TaskManager provides hooks for:
    1. Deciding when to create tasks vs return messages
    2. Processing tasks in background
    3. Updating task status during processing
    4. Retrieving task status for GetTask API

    Consumers implement their own logic for task creation, processing,
    and storage using the provided TaskStore interface.
    """

    def __init__(self, task_store: TaskStore):
        """Initialize TaskManager with storage backend.

        Args:
            task_store: Storage backend for task persistence
        """
        self.task_store = task_store

    # Required methods

    @abstractmethod
    async def should_create_task(self, request: InvocationRequest) -> bool:
        """Determine if this request should create a task vs return message.

        Called by MessageHandler when TaskManager is configured.

        Consider:
        - Client type (chat vs agent)
        - Message content (keywords, patterns)
        - Operation complexity
        - Expected duration

        Args:
            request: The incoming A2A invocation request

        Returns:
            True if task should be created, False for immediate message response
        """
        pass

    @abstractmethod
    async def on_send_task(self, task: A2ATask, request: InvocationRequest) -> None:
        """Called when agent creates a task.

        Consumer implements task creation and background processing logic:
        - Store task using upsert_task()
        - Start background processing (worker, subagent, etc.)
        - Update task status during processing

        Args:
            task: Task information to process
        """
        pass

    # Optional methods

    async def should_process_task(self, request: InvocationRequest) -> bool:
        """Determine if this request should be processed by the TaskManager. This should return True if the requester
        sends a message to provide task related information. Consumer should then implement handling behavior with
        `on_receive_task` below.

        Called by MessageHandler when TaskManager is configured

        Consider:
        - Does this SendMessage request have a taskId?

        Args:
            request: The incoming A2A invocation request

        Returns:
            True if this request should be handled by TaskManager, False if not
        """
        return False

    async def on_receive_task(self, task: A2ATask, request: InvocationRequest) -> None:
        """Called when a should_process_task resolves to True, normally if the incoming request has a taskId

        Override to customize behavior when a SendMessage request is received with a taskId

        Args:
            task: The Task created in direct response
            request: The incoming request that has a taskId
        """
        pass

    def get_task_process_message(self, request: InvocationRequest) -> A2AMessage:
        """Get initial response message when task is being processed.

        Override to customize the message shown to the caller immediately
        after task processing (before background processing completes).

        Args:
            request: The incoming request that triggered task creation

        Returns:
            A2AMessage with initial response (default: "I'm working on your request...")
        """
        return A2AMessage(
            role="agent",
            parts=[{"text": "I'm working on processing your task request", "kind": "text"}],
            messageId=str(uuid.uuid4()),
            kind="message",
            contextId=request.message.contextId,
        )

    def get_task_creation_message(self, request: InvocationRequest) -> A2AMessage:
        """Get initial response message when task is created.

        Override to customize the message shown to users immediately
        after task creation (before background processing completes).

        Args:
            request: The incoming request that triggered task creation

        Returns:
            A2AMessage with initial response (default: "I'm working on your request...")
        """
        return A2AMessage(
            role="agent",
            parts=[{"text": "I'm working on your request and have created a task", "kind": "text"}],
            messageId=str(uuid.uuid4()),
            kind="message",
            contextId=request.message.contextId,
        )

    def supports_auto_upgrade(self) -> bool:
        """Enable automatic task upgrade on timeout.

        TODO: Auto-upgrade functionality not yet implemented in MessageHandler.
        When implemented, MessageHandler will automatically upgrade to task
        if processing exceeds timeout threshold.

        Returns:
            True to enable auto-upgrade, False to disable (default)
        """
        return False

    async def on_get_task(self, task_id: str) -> Optional[A2ATask]:
        """Called when GetTask API is invoked.

        Default implementation uses TaskStore. Override for custom logic.

        Args:
            task_id: The task ID to retrieve

        Returns:
            A2ATask with current state, or None if not found
        """
        return await self.task_store.get_task(task_id)

    async def upsert_task(self, task: A2ATask) -> None:
        """Store or update task information.

        Default implementation uses TaskStore. Override for custom logic.

        Note: Not atomic. For concurrent environments, override with atomic operations.

        Args:
            task: Task information to store/update
        """
        existing = await self.task_store.get_task(task.id)
        if existing:
            await self.task_store.update_task(task)
        else:
            await self.task_store.store_task(task)
