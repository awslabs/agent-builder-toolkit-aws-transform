# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the job tools functionality.
"""

from unittest import mock

import pytest
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext

# Now import the module
from agent_builder_agentic_mcp.server._job_tools import (
    create_worklog,
    delete_job_plan_step,
    get_job,
    list_job_plan_steps,
    list_worklogs,
    put_job_plan,
    update_job_plan_step,
    update_job_status,
)


@pytest.fixture
def mock_request_context():
    """Mock the request context injection."""

    def mock_inject(kwargs):
        # Preserve the original kwargs and add requestContext
        result = kwargs.copy() if kwargs else {}
        result["requestContext"] = AgenticRequestContext(
            job_id="test-job-id",
            workspace_id="test-workspace-id",
            agent_instance_id="test-agent-id",
            authorization_token="test-token",
        )
        return result

    patcher = mock.patch(
        "agent_builder_agentic_mcp.server._job_tools._inject_qt_request_context", mock_inject
    )
    patcher.start()
    yield mock_inject
    patcher.stop()


@pytest.fixture
def mock_atx_client():
    magic_mock = mock.MagicMock()
    with mock.patch(
        "agent_builder_agentic_mcp.server._job_tools.atx_agenticapi_client"
    ) as mock_atx_client:
        mock_atx_client.return_value = magic_mock
        yield mock_atx_client.return_value


@pytest.fixture
def sample_job():
    """Return a sample job response."""
    return {
        "jobId": "test-job-id",
        "workspaceId": "test-workspace-id",
        "status": "IN_PROGRESS",
        "createdAt": "2025-05-23T18:00:00Z",
        "objective": "Test objective",
    }


@pytest.mark.anyio
async def test_get_job(mock_atx_client, mock_request_context, sample_job):
    """Test getting job information."""
    mock_atx_client.get_job.return_value = {"job": sample_job}

    result = await get_job()

    mock_atx_client.get_job.assert_called_once()
    call_args = mock_atx_client.get_job.call_args[1]
    assert call_args["includeObjective"] is True
    assert result == {"job": sample_job}


@pytest.mark.anyio
async def test_get_job_error_handling(mock_atx_client, mock_request_context):
    """Test error handling in get_job."""
    mock_atx_client.get_job.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await get_job()

    assert "Test error" in str(exc_info.value)
    mock_atx_client.get_job.assert_called_once()


@pytest.mark.anyio
async def test_update_job_status(mock_atx_client, mock_request_context):
    """Test updating job status."""
    # Call the function
    result = await update_job_status(status="COMPLETED")

    # Verify the mock was called with the right parameters
    mock_atx_client.update_job_status.assert_called_once()
    call_args = mock_atx_client.update_job_status.call_args[1]
    assert call_args["status"] == "COMPLETED"
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_create_worklog(mock_atx_client, mock_request_context):
    """Test creating a worklog entry."""
    # Sample worklog parameters
    description = "Test worklog entry"
    timestamp = "1626912000000"  # Example timestamp
    plan_step_id = "step-123"
    action = "TEST_ACTION"
    start_time = "1626911000000"  # Example start time
    artifact_id = "artifact-456"

    # Call the function with all parameters
    result = await create_worklog(
        description=description,
        timestamp=timestamp,
        plan_step_id=plan_step_id,
        action=action,
        start_time=start_time,
        artifact_id=artifact_id,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_worklog.assert_called_once()
    call_args = mock_atx_client.create_worklog.call_args[1]

    # Check that the worklog was constructed correctly
    assert "worklog" in call_args
    worklog = call_args["worklog"]
    assert worklog["description"] == description
    assert worklog["timestamp"] == timestamp
    assert worklog["attributeMap"]["STEP_ID"] == plan_step_id
    assert worklog["attributeMap"]["ACTION"] == action
    assert worklog["attributeMap"]["START_TIME"] == start_time
    assert worklog["attributeMap"]["ARTIFACT_ID"] == artifact_id
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_put_job_plan(mock_atx_client, mock_request_context):
    """Test creating or updating a job plan."""
    # Sample plan and mode data
    plan_data = {
        "steps": [
            {"stepId": "step-1", "title": "Test step", "description": "Test step description"}
        ]
    }
    mode_data = {"type": "OVERRIDE"}

    # Mock the response
    mock_atx_client.put_job_plan.return_value = {
        "status": "SUCCESS",
        "mappings": {"step-1": "mapped-step-1"},
    }

    # Call the function
    result = await put_job_plan(plan=plan_data, mode=mode_data)

    # Verify the mock was called with the right parameters
    mock_atx_client.put_job_plan.assert_called_once()
    call_args = mock_atx_client.put_job_plan.call_args[1]
    assert call_args["plan"] == plan_data
    assert call_args["mode"] == mode_data
    assert "requestContext" in call_args

    # Verify the result
    assert result["status"] == "SUCCESS"
    assert result["mappings"] == {"step-1": "mapped-step-1"}


@pytest.mark.anyio
async def test_list_job_plan_steps(mock_atx_client, mock_request_context):
    """Test listing job plan steps."""
    # Sample steps data
    steps_data = [
        {"stepId": "step-1", "title": "Test step 1", "status": "COMPLETED"},
        {"stepId": "step-2", "title": "Test step 2", "status": "IN_PROGRESS"},
    ]

    # Mock the response
    mock_atx_client.list_job_plan_steps.return_value = {
        "steps": steps_data,
        "nextToken": "next-page-token",
    }

    # Call the function with optional parameters
    result = await list_job_plan_steps(
        parent_step_id="parent-step", max_results=10, next_token="page-token"
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.list_job_plan_steps.assert_called_once()
    call_args = mock_atx_client.list_job_plan_steps.call_args[1]
    assert call_args["parentStepId"] == "parent-step"
    assert call_args["maxResults"] == 10
    assert call_args["nextToken"] == "page-token"
    assert "requestContext" in call_args

    # Verify the result
    assert result["steps"] == steps_data
    assert result["nextToken"] == "next-page-token"


@pytest.mark.anyio
async def test_update_job_plan_step(mock_atx_client, mock_request_context):
    """Test updating a job plan step."""
    # Sample plan step data
    plan_step_data = {"stepId": "step-1", "status": "COMPLETED", "output": {"result": "Success"}}

    # Call the function
    result = await update_job_plan_step(plan_step=plan_step_data)

    # Verify the mock was called with the right parameters
    mock_atx_client.update_job_plan_step.assert_called_once()
    call_args = mock_atx_client.update_job_plan_step.call_args[1]
    assert call_args["planStep"] == plan_step_data
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_delete_job_plan_step(mock_atx_client, mock_request_context):
    """Test deleting a job plan step."""
    # Call the function
    result = await delete_job_plan_step(step_id="step-1")

    # Verify the mock was called with the right parameters
    mock_atx_client.delete_job_plan_step.assert_called_once()
    call_args = mock_atx_client.delete_job_plan_step.call_args[1]
    assert call_args["stepId"] == "step-1"
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_update_job_status_with_all_params(mock_atx_client, mock_request_context):
    """Test updating job status with all parameters."""
    # Sample status info
    status_info = {"message": "Job completed successfully", "details": {"runtime": 120}}

    # Call the function with all parameters
    result = await update_job_status(status="COMPLETED", status_info=status_info)

    # Verify the mock was called with the right parameters
    mock_atx_client.update_job_status.assert_called_once()
    call_args = mock_atx_client.update_job_status.call_args[1]
    assert call_args["status"] == "COMPLETED"
    assert call_args["statusInfo"] == status_info
    assert "idempotencyToken" in call_args  # Check that a UUID was generated
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_create_worklog_with_idempotency_token(mock_atx_client, mock_request_context):
    """Test creating a worklog entry with idempotency token."""
    # Sample worklog parameters
    description = "Test worklog entry with token"
    plan_step_id = "step-456"

    # Call the function with minimal required parameters
    result = await create_worklog(
        description=description,
        timestamp=None,
        plan_step_id=plan_step_id,
        action=None,
        start_time=None,
        artifact_id=None,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_worklog.assert_called_once()
    call_args = mock_atx_client.create_worklog.call_args[1]

    # Check that the worklog was constructed correctly
    assert "worklog" in call_args
    worklog = call_args["worklog"]
    assert worklog["description"] == description
    assert "timestamp" in worklog  # Should have a timestamp even if not provided
    assert worklog["attributeMap"]["STEP_ID"] == plan_step_id
    assert "ACTION" not in worklog["attributeMap"]
    assert "START_TIME" not in worklog["attributeMap"]
    assert "ARTIFACT_ID" not in worklog["attributeMap"]

    # Check for idempotency token
    assert "idempotencyToken" in call_args
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_put_job_plan_with_idempotency_token(mock_atx_client, mock_request_context):
    """Test creating or updating a job plan with idempotency token."""
    # Sample plan and mode data
    plan_data = {
        "steps": [
            {
                "stepId": "step-1",
                "title": "Test step with token",
                "description": "Test step description",
            }
        ]
    }
    mode_data = {"type": "APPEND"}

    # Mock the response
    mock_atx_client.put_job_plan.return_value = {"status": "SUCCESS"}

    # Call the function
    result = await put_job_plan(plan=plan_data, mode=mode_data)

    # Verify the mock was called with the right parameters
    mock_atx_client.put_job_plan.assert_called_once()
    call_args = mock_atx_client.put_job_plan.call_args[1]
    assert call_args["plan"] == plan_data
    assert call_args["mode"] == mode_data
    assert "idempotencyToken" in call_args  # Check that a UUID was generated
    assert "requestContext" in call_args

    # Verify the result
    assert result["status"] == "SUCCESS"


@pytest.mark.anyio
async def test_update_job_plan_step_with_idempotency_token(mock_atx_client, mock_request_context):
    """Test updating a job plan step with idempotency token."""
    # Sample plan step data
    plan_step_data = {"stepId": "step-1", "status": "COMPLETED", "output": {"result": "Success"}}

    # Call the function
    result = await update_job_plan_step(plan_step=plan_step_data)

    # Verify the mock was called with the right parameters
    mock_atx_client.update_job_plan_step.assert_called_once()
    call_args = mock_atx_client.update_job_plan_step.call_args[1]
    assert call_args["planStep"] == plan_step_data
    assert "idempotencyToken" in call_args  # Check that a UUID was generated
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_delete_job_plan_step_with_idempotency_token(mock_atx_client, mock_request_context):
    """Test deleting a job plan step with idempotency token."""
    # Call the function
    result = await delete_job_plan_step(step_id="step-1")

    # Verify the mock was called with the right parameters
    mock_atx_client.delete_job_plan_step.assert_called_once()
    call_args = mock_atx_client.delete_job_plan_step.call_args[1]
    assert call_args["stepId"] == "step-1"
    assert "idempotencyToken" in call_args  # Check that a UUID was generated
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_list_job_plan_steps_no_params(mock_atx_client, mock_request_context):
    """Test listing job plan steps with no parameters."""
    # Sample steps data
    steps_data = [{"stepId": "step-1", "title": "Test step 1", "status": "COMPLETED"}]

    # Mock the response
    mock_atx_client.list_job_plan_steps.return_value = {"steps": steps_data}

    # Call the function with no parameters
    result = await list_job_plan_steps()

    # Verify the mock was called with the right parameters
    mock_atx_client.list_job_plan_steps.assert_called_once()
    call_args = mock_atx_client.list_job_plan_steps.call_args[1]
    assert "requestContext" in call_args
    assert len(call_args) == 1  # Only requestContext should be present

    # Verify the result
    assert result["steps"] == steps_data
    assert "nextToken" not in result


@pytest.mark.anyio
async def test_update_job_status_error(mock_atx_client, mock_request_context):
    """Test error handling in update_job_status."""
    # Set up the mock to raise an exception
    mock_atx_client.update_job_status.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await update_job_status(status="FAILED")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.update_job_status.assert_called_once()


@pytest.mark.anyio
async def test_create_worklog_error(mock_atx_client, mock_request_context):
    """Test error handling in create_worklog."""
    # Set up the mock to raise an exception
    mock_atx_client.create_worklog.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await create_worklog(
            description="Test description",
            timestamp=None,
            plan_step_id="step-789",
            action=None,
            start_time=None,
            artifact_id=None,
        )

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.create_worklog.assert_called_once()


@pytest.mark.anyio
async def test_put_job_plan_error(mock_atx_client, mock_request_context):
    """Test error handling in put_job_plan."""
    # Sample plan and mode data
    plan_data = {"steps": [{"stepId": "step-1"}]}
    mode_data = {"type": "OVERRIDE"}

    # Set up the mock to raise an exception
    mock_atx_client.put_job_plan.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await put_job_plan(plan=plan_data, mode=mode_data)

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.put_job_plan.assert_called_once()


@pytest.mark.anyio
async def test_list_job_plan_steps_error(mock_atx_client, mock_request_context):
    """Test error handling in list_job_plan_steps."""
    # Set up the mock to raise an exception
    mock_atx_client.list_job_plan_steps.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await list_job_plan_steps()

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.list_job_plan_steps.assert_called_once()


@pytest.mark.anyio
async def test_update_job_plan_step_error(mock_atx_client, mock_request_context):
    """Test error handling in update_job_plan_step."""
    # Sample plan step data
    plan_step_data = {"stepId": "step-1", "status": "COMPLETED"}

    # Set up the mock to raise an exception
    mock_atx_client.update_job_plan_step.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await update_job_plan_step(plan_step=plan_step_data)

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.update_job_plan_step.assert_called_once()


@pytest.mark.anyio
async def test_delete_job_plan_step_error(mock_atx_client, mock_request_context):
    """Test error handling in delete_job_plan_step."""
    # Set up the mock to raise an exception
    mock_atx_client.delete_job_plan_step.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await delete_job_plan_step(step_id="step-1")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.delete_job_plan_step.assert_called_once()


@pytest.mark.anyio
async def test_list_worklogs_with_step_id(mock_atx_client, mock_request_context):
    """Test listing worklogs filtered by plan_step_id."""
    worklogs_data = [
        {
            "timestamp": "1626912000000",
            "description": "Test worklog 1",
            "attributeMap": {"STEP_ID": "step-123"},
        },
        {
            "timestamp": "1626913000000",
            "description": "Test worklog 2",
            "attributeMap": {"STEP_ID": "step-123"},
        },
    ]

    mock_atx_client.list_worklogs.return_value = {
        "worklogs": worklogs_data,
        "nextToken": "next-token",
    }

    result = await list_worklogs(plan_step_id="step-123")

    mock_atx_client.list_worklogs.assert_called_once()
    call_args = mock_atx_client.list_worklogs.call_args[1]
    assert call_args["worklogFilter"]["stepIdFilter"]["stepId"] == "step-123"
    assert "requestContext" in call_args
    assert result["worklogs"] == worklogs_data
    assert result["nextToken"] == "next-token"


@pytest.mark.anyio
async def test_list_worklogs_with_time_filter(mock_atx_client, mock_request_context):
    """Test listing worklogs filtered by time range."""
    worklogs_data = [{"timestamp": "1626912000000", "description": "Test worklog"}]

    mock_atx_client.list_worklogs.return_value = {"worklogs": worklogs_data}

    result = await list_worklogs(start_time="1626900000000", end_time="1626920000000")

    mock_atx_client.list_worklogs.assert_called_once()
    call_args = mock_atx_client.list_worklogs.call_args[1]
    assert call_args["worklogFilter"]["timeFilter"]["startTime"] == "1626900000000"
    assert call_args["worklogFilter"]["timeFilter"]["endTime"] == "1626920000000"
    assert result["worklogs"] == worklogs_data


@pytest.mark.anyio
async def test_list_worklogs_with_step_and_time(mock_atx_client, mock_request_context):
    """Test listing worklogs with both step_id and time filters."""
    worklogs_data = [{"timestamp": "1626912000000", "description": "Test worklog"}]

    mock_atx_client.list_worklogs.return_value = {"worklogs": worklogs_data}

    result = await list_worklogs(
        plan_step_id="step-123", start_time="1626900000000", end_time="1626920000000"
    )

    mock_atx_client.list_worklogs.assert_called_once()
    call_args = mock_atx_client.list_worklogs.call_args[1]
    assert call_args["worklogFilter"]["stepIdFilter"]["stepId"] == "step-123"
    assert call_args["worklogFilter"]["stepIdFilter"]["timeFilter"]["startTime"] == "1626900000000"
    assert call_args["worklogFilter"]["stepIdFilter"]["timeFilter"]["endTime"] == "1626920000000"
    assert result["worklogs"] == worklogs_data


@pytest.mark.anyio
async def test_list_worklogs_no_filters(mock_atx_client, mock_request_context):
    """Test listing all worklogs without filters."""
    worklogs_data = [{"timestamp": "1626912000000", "description": "Test worklog"}]

    mock_atx_client.list_worklogs.return_value = {"worklogs": worklogs_data}

    result = await list_worklogs()

    mock_atx_client.list_worklogs.assert_called_once()
    call_args = mock_atx_client.list_worklogs.call_args[1]
    assert "worklogFilter" not in call_args
    assert result["worklogs"] == worklogs_data


@pytest.mark.anyio
async def test_list_worklogs_error(mock_atx_client, mock_request_context):
    """Test error handling in list_worklogs."""
    mock_atx_client.list_worklogs.side_effect = Exception("Test error")

    with pytest.raises(Exception) as exc_info:
        await list_worklogs()

    assert "Test error" in str(exc_info.value)
    mock_atx_client.list_worklogs.assert_called_once()
