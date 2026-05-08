# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Task handler for GetTask operations
"""

import logging
import uuid
from datetime import datetime, timezone

from agent_builder_sdk.custom_types.common_types import A2AError, A2AErrorCode
from agent_builder_sdk.custom_types.task_types import (
    A2ATask,
    GetTaskRequest,
    GetTaskResponse,
    TaskState,
    TaskStatus,
)
from agent_builder_sdk.env_var import get_agent_context_from_env

logger = logging.getLogger(__name__)


class TaskHandler:
    """Handles task-related operations for the base agent."""

    def __init__(self, task_manager=None):
        """Initialize TaskHandler.

        Args:
            task_manager: Optional TaskManager for task retrieval (experimental)
        """
        self.task_manager = task_manager

    async def get_task(self, request: GetTaskRequest) -> GetTaskResponse:
        """
        Retrieve a task by ID.

        Args:
            request: GetTask request parameters

        Returns:
            GetTaskResponse with task data or error
        """
        logger.info(f"Processing GetTask request for task: {request.id}")

        # If TaskManager configured, use it
        if self.task_manager:
            try:
                task = await self.task_manager.on_get_task(request.id)
                if task:
                    logger.info(f"Successfully retrieved task: {request.id}")
                    return GetTaskResponse(result=task)
                else:
                    logger.warning(f"Task not found: {request.id}")
                    return GetTaskResponse(
                        error=A2AError(
                            code=A2AErrorCode.TASK_NOT_FOUND,
                            message=f"Task not found: {request.id}",
                        )
                    )
            except Exception as e:
                logger.error(f"Error retrieving task: {e}")
                return GetTaskResponse(
                    error=A2AError(
                        code=A2AErrorCode.INTERNAL_ERROR,
                        message=f"Error retrieving task: {str(e)}",
                    )
                )

        # Fall back to legacy placeholder implementation
        return self._get_task_legacy(request)

    def _get_task_legacy(self, request: GetTaskRequest) -> GetTaskResponse:
        """Legacy placeholder implementation (deprecated)."""
        logger.info(f"Using legacy GetTask for task: {request.id}")
        """
        Retrieve a task by ID.

        Args:
            request: GetTask request parameters

        Returns:
            GetTaskResponse with task data or error
        """
        logger.info(f"Processing GetTask request for task: {request.id}")

        # TODO: Implement actual task retrieval logic
        # Currently if the task id = job id, we return a placeholder implementation.
        try:
            context = get_agent_context_from_env()
            if request.id != context.job_id:
                logger.warning(f"Task not found: {request.id}")
                return GetTaskResponse(
                    error=A2AError(
                        code=A2AErrorCode.TASK_NOT_FOUND,
                        message=f"Task not found: {request.id}",
                    )
                )
        except ValueError as e:
            logger.error(f"Failed to get agent context: {type(e).__name__}: {str(e)}")
            return GetTaskResponse(
                error=A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR,
                    message="Internal error when retrieving task.",
                )
            )

        logger.info(f"Returning placeholder task for: {request.id}")
        task = A2ATask(
            id=request.id,
            contextId=str(uuid.uuid4()),
            kind="task",
            status=TaskStatus(
                state=TaskState.WORKING,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

        logger.info(f"Successfully retrieved task: {request.id}")
        return GetTaskResponse(result=task)
