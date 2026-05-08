# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for TaskHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from agent_builder_sdk.custom_types.common_types import A2AErrorCode
from agent_builder_sdk.custom_types.task_types import (
    A2ATask,
    GetTaskRequest,
    TaskState,
    TaskStatus,
)
from agent_builder_sdk.task_handler import TaskHandler


@pytest.fixture
def sample_task():
    """Create a sample task."""
    from agent_builder_sdk.custom_types.common_types import A2AMessage

    return A2ATask(
        id="test-task-123",
        contextId="ctx-456",
        status=TaskStatus(
            state=TaskState.COMPLETED,
            message=A2AMessage(
                role="agent",
                parts=[{"kind": "text", "text": "Task completed"}],
                messageId="msg-1",
                kind="message",
                contextId="ctx-456",
            ),
        ),
    )


class TestTaskHandlerWithTaskManager:
    """Tests for TaskHandler with TaskManager configured."""

    @pytest.mark.asyncio
    async def test_get_task_success(self, sample_task):
        """Test successful task retrieval with TaskManager."""
        mock_task_manager = Mock()
        mock_task_manager.on_get_task = AsyncMock(return_value=sample_task)

        handler = TaskHandler(task_manager=mock_task_manager)
        request = GetTaskRequest(id="test-task-123")

        response = await handler.get_task(request)

        assert response.result is not None
        assert response.error is None
        assert response.result.id == "test-task-123"
        assert response.result.status.state == TaskState.COMPLETED
        mock_task_manager.on_get_task.assert_called_once_with("test-task-123")

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        """Test task not found with TaskManager."""
        mock_task_manager = Mock()
        mock_task_manager.on_get_task = AsyncMock(return_value=None)

        handler = TaskHandler(task_manager=mock_task_manager)
        request = GetTaskRequest(id="nonexistent")

        response = await handler.get_task(request)

        assert response.result is None
        assert response.error is not None
        assert response.error.code == A2AErrorCode.TASK_NOT_FOUND
        assert "not found" in response.error.message.lower()

    @pytest.mark.asyncio
    async def test_get_task_manager_exception(self):
        """Test TaskManager raises exception."""
        mock_task_manager = Mock()
        mock_task_manager.on_get_task = AsyncMock(side_effect=Exception("Database error"))

        handler = TaskHandler(task_manager=mock_task_manager)
        request = GetTaskRequest(id="test-task-123")

        response = await handler.get_task(request)

        assert response.result is None
        assert response.error is not None
        assert response.error.code == A2AErrorCode.INTERNAL_ERROR
        assert "error retrieving task" in response.error.message.lower()


class TestTaskHandlerLegacy:
    """Tests for TaskHandler legacy implementation (no TaskManager)."""

    @pytest.mark.asyncio
    async def test_get_task_feature_enabled_wrong_task_id(self, monkeypatch):
        """Test GetTask with wrong task ID."""
        from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext

        # Mock get_agent_context_from_env to return context
        def mock_get_context():
            return AgenticApiRequestContext(
                job_id="job-123",
                workspace_id="ws-456",
                agent_instance_id="agent-789",
                authorization_token="token",
            )

        import agent_builder_sdk.task_handler

        monkeypatch.setattr(
            agent_builder_sdk.task_handler, "get_agent_context_from_env", mock_get_context
        )

        handler = TaskHandler()
        request = GetTaskRequest(id="wrong-task-id")

        response = await handler.get_task(request)

        assert response.result is None
        assert response.error is not None
        assert response.error.code == A2AErrorCode.TASK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_task_feature_enabled_correct_task_id(self, monkeypatch):
        """Test GetTask with correct task ID returns placeholder."""
        from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext

        # Mock get_agent_context_from_env to return context
        def mock_get_context():
            return AgenticApiRequestContext(
                job_id="job-123",
                workspace_id="ws-456",
                agent_instance_id="agent-789",
                authorization_token="token",
            )

        import agent_builder_sdk.task_handler

        monkeypatch.setattr(
            agent_builder_sdk.task_handler, "get_agent_context_from_env", mock_get_context
        )

        handler = TaskHandler()
        request = GetTaskRequest(id="job-123")

        response = await handler.get_task(request)

        assert response.result is not None
        assert response.error is None
        assert response.result.id == "job-123"
        assert response.result.status.state == TaskState.WORKING

    @pytest.mark.asyncio
    async def test_get_task_missing_env_vars(self, monkeypatch):
        """Test GetTask with missing environment variables."""

        # Mock get_agent_context_from_env to raise ValueError
        def mock_get_context():
            raise ValueError("Missing required environment variables")

        import agent_builder_sdk.task_handler

        monkeypatch.setattr(
            agent_builder_sdk.task_handler, "get_agent_context_from_env", mock_get_context
        )

        handler = TaskHandler()
        request = GetTaskRequest(id="test-task-123")

        response = await handler.get_task(request)

        assert response.result is None
        assert response.error is not None
        assert response.error.code == A2AErrorCode.INTERNAL_ERROR
        assert "internal error" in response.error.message.lower()
