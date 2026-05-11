# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the HITL tools functionality.
"""

import os
from unittest import mock

import pytest
from agent_builder_agentic_mcp import env_var
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext
from agent_builder_agentic_mcp.server._hitl_tools import (
    close_hitl_task,
    create_hitl_task,
    get_hitl_task,
    list_hitl_tasks,
    start_hitl_task,
)


@pytest.fixture
def mock_environment():
    """Set up required environment variables."""
    original_env = dict(os.environ)
    os.environ[env_var.ENV_KEY_QT_JOB_ID] = "test-job-id"
    os.environ[env_var.ENV_KEY_QT_WORKSPACE_ID] = "test-workspace-id"
    os.environ[env_var.ENV_KEY_QT_AGENT_INSTANCE_ID] = "test-agent-id"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_atx_client(mock_environment):
    """Mock the ATX Agentic API client."""
    with mock.patch(
        "agent_builder_agentic_mcp.server._hitl_tools.atx_agenticapi_client"
    ) as mock_client:
        mock_client.return_value = mock.MagicMock()
        yield mock_client.return_value


@pytest.fixture
def mock_request_context():
    """Mock the request context injection."""
    with mock.patch(
        "agent_builder_agentic_mcp.server._inject_qt_request_context._get_request_context"
    ) as mock_context:
        mock_context.return_value = AgenticRequestContext(
            job_id="test-job-id",
            workspace_id="test-workspace-id",
            agent_instance_id="test-agent-id",
            authorization_token="test-token",
        )
        yield mock_context


@pytest.fixture
def mock_auth_token():
    """Mock the get_auth_token function to avoid file access issues."""
    with mock.patch(
        "agent_builder_agentic_mcp.server._inject_qt_request_context.get_auth_token",
        return_value="test-auth-token",
    ) as mock_token:
        yield mock_token


@pytest.fixture
def sample_hitl_task():
    """Return a sample HITL task response."""
    return {
        "hitlTaskId": "test-task-id",
        "uxComponentId": "test-component",
        "description": "Test description",
        "title": "Test Title",
        "status": "CREATED",
        "createdAt": "2025-05-23T18:00:00Z",
    }


@pytest.mark.anyio
async def test_create_hitl_task_minimal(mock_atx_client, mock_request_context):
    """Test creating a HITL task with minimal required parameters."""
    mock_atx_client.create_hitl_task.return_value = {"hitlTaskId": "test-task-id"}

    result = await create_hitl_task(
        ux_component_id="test-component", description="Test description", title="Test Title"
    )

    mock_atx_client.create_hitl_task.assert_called_once()
    call_args = mock_atx_client.create_hitl_task.call_args[1]

    assert call_args["uxComponentId"] == "test-component"
    assert call_args["description"] == "Test description"
    assert call_args["title"] == "Test Title"
    assert "requestContext" in call_args
    assert result == {"hitl_task_id": "test-task-id"}


@pytest.mark.anyio
async def test_create_hitl_task_with_all_params(mock_atx_client, mock_request_context):
    """Test creating a HITL task with all optional parameters."""
    mock_atx_client.create_hitl_task.return_value = {"hitlTaskId": "test-task-id"}

    result = await create_hitl_task(
        ux_component_id="test-component",
        description="Test description",
        title="Test Title",
        severity="HIGH",
        hitl_task_type="APPROVAL",
        step_id="step-123",
        blocking_type="BLOCKING",
        hitl_request_artifact={"key": "value"},
        expired_at="2025-06-01T00:00:00Z",
        tag="test-tag",
    )

    mock_atx_client.create_hitl_task.assert_called_once()
    call_args = mock_atx_client.create_hitl_task.call_args[1]

    assert call_args["uxComponentId"] == "test-component"
    assert call_args["description"] == "Test description"
    assert call_args["title"] == "Test Title"
    assert call_args["severity"] == "HIGH"
    assert call_args["hitlTaskType"] == "APPROVAL"
    assert call_args["stepId"] == "step-123"
    assert call_args["blockingType"] == "BLOCKING"
    assert call_args["hitlRequestArtifact"] == {"key": "value"}
    assert call_args["expiredAt"] == "2025-06-01T00:00:00Z"
    assert call_args["tag"] == "test-tag"
    assert "idempotencyToken" in call_args
    assert "requestContext" in call_args
    assert result == {"hitl_task_id": "test-task-id"}


@pytest.mark.anyio
async def test_create_hitl_task_error_handling(mock_atx_client, mock_request_context):
    """Test error handling in create_hitl_task."""
    mock_atx_client.create_hitl_task.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await create_hitl_task(
            ux_component_id="test-component", description="Test description", title="Test Title"
        )

    assert "Test error" in str(exc_info.value)
    mock_atx_client.create_hitl_task.assert_called_once()


@pytest.mark.anyio
async def test_get_hitl_task(
    mock_atx_client, mock_request_context, sample_hitl_task, mock_auth_token
):
    """Test getting a HITL task."""
    mock_atx_client.get_hitl_task.return_value = {"hitlTask": sample_hitl_task}

    result = await get_hitl_task("test-task-id")

    mock_atx_client.get_hitl_task.assert_called_once()
    assert result == {"hitl_task": sample_hitl_task}


@pytest.mark.anyio
async def test_get_hitl_task_error_handling(mock_atx_client, mock_request_context, mock_auth_token):
    """Test error handling in get_hitl_task."""
    mock_atx_client.get_hitl_task.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await get_hitl_task("test-task-id")

    assert "Test error" in str(exc_info.value)
    mock_atx_client.get_hitl_task.assert_called_once()


@pytest.mark.anyio
async def test_start_hitl_task(mock_atx_client, mock_request_context):
    """Test starting a HITL task."""
    mock_atx_client.start_hitl_task.return_value = {"hitlTaskStatus": "STARTED"}

    result = await start_hitl_task("test-task-id")

    mock_atx_client.start_hitl_task.assert_called_once()
    assert result == {"hitl_task_status": "STARTED"}


@pytest.mark.anyio
async def test_start_hitl_task_with_options(mock_atx_client, mock_request_context):
    """Test starting a HITL task with optional parameters."""
    mock_atx_client.start_hitl_task.return_value = {"hitlTaskStatus": "STARTED"}

    result = await start_hitl_task("test-task-id", first_in_chain=True)

    mock_atx_client.start_hitl_task.assert_called_once()
    call_args = mock_atx_client.start_hitl_task.call_args[1]
    assert call_args["hitlTaskId"] == "test-task-id"
    assert call_args["firstInChain"] is True
    assert "idempotencyToken" in call_args
    assert result == {"hitl_task_status": "STARTED"}


@pytest.mark.anyio
async def test_start_hitl_task_error_handling(mock_atx_client, mock_request_context):
    """Test error handling in start_hitl_task."""
    mock_atx_client.start_hitl_task.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await start_hitl_task("test-task-id")

    assert "Test error" in str(exc_info.value)
    mock_atx_client.start_hitl_task.assert_called_once()


@pytest.mark.anyio
async def test_close_hitl_task(mock_atx_client, mock_request_context):
    """Test closing a HITL task."""
    mock_atx_client.close_hitl_task.return_value = {"hitlTaskStatus": "CLOSED"}

    result = await close_hitl_task("test-task-id", "COMPLETED")

    mock_atx_client.close_hitl_task.assert_called_once()
    assert result == {"hitl_task_status": "CLOSED"}


@pytest.mark.anyio
async def test_close_hitl_task_with_idempotency_token(mock_atx_client, mock_request_context):
    """Test closing a HITL task with idempotency token."""
    mock_atx_client.close_hitl_task.return_value = {"hitlTaskStatus": "CLOSED"}

    result = await close_hitl_task("test-task-id", "COMPLETED")

    mock_atx_client.close_hitl_task.assert_called_once()
    call_args = mock_atx_client.close_hitl_task.call_args[1]
    assert call_args["hitlTaskId"] == "test-task-id"
    assert call_args["closureType"] == "COMPLETED"
    assert "idempotencyToken" in call_args
    assert result == {"hitl_task_status": "CLOSED"}


@pytest.mark.anyio
async def test_close_hitl_task_error_handling(mock_atx_client, mock_request_context):
    """Test error handling in close_hitl_task."""
    mock_atx_client.close_hitl_task.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await close_hitl_task("test-task-id", "COMPLETED")

    assert "Test error" in str(exc_info.value)
    mock_atx_client.close_hitl_task.assert_called_once()


@pytest.mark.anyio
async def test_list_hitl_tasks(mock_atx_client, mock_request_context, sample_hitl_task):
    """Test listing HITL tasks."""
    mock_atx_client.list_hitl_tasks.return_value = {
        "hitlTasks": [sample_hitl_task],
        "nextToken": "next-page-token",
    }

    result = await list_hitl_tasks("TEST_TYPE")

    mock_atx_client.list_hitl_tasks.assert_called_once()
    assert "hitl_tasks" in result
    assert "next_token" in result
    assert len(result["hitl_tasks"]) == 1
    assert result["next_token"] == "next-page-token"


@pytest.mark.anyio
async def test_list_hitl_tasks_with_options(
    mock_atx_client, mock_request_context, sample_hitl_task
):
    """Test listing HITL tasks with all optional parameters."""
    mock_atx_client.list_hitl_tasks.return_value = {
        "hitlTasks": [sample_hitl_task],
        "nextToken": "next-page-token",
    }

    result = await list_hitl_tasks(
        "TEST_TYPE", task_filter={"status": "OPEN"}, max_results=10, next_token="current-page-token"
    )

    mock_atx_client.list_hitl_tasks.assert_called_once()
    call_args = mock_atx_client.list_hitl_tasks.call_args[1]
    assert call_args["taskType"] == "TEST_TYPE"
    assert call_args["taskFilter"] == {"status": "OPEN"}
    assert call_args["maxResults"] == 10
    assert call_args["nextToken"] == "current-page-token"
    assert "hitl_tasks" in result
    assert "next_token" in result


@pytest.mark.anyio
async def test_list_hitl_tasks_error_handling(mock_atx_client, mock_request_context):
    """Test error handling in list_hitl_tasks."""
    mock_atx_client.list_hitl_tasks.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await list_hitl_tasks("TEST_TYPE")

    assert "Test error" in str(exc_info.value)
    mock_atx_client.list_hitl_tasks.assert_called_once()
