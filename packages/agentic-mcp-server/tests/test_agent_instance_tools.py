# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the agent instance tools functionality.
"""

from unittest import mock

import pytest
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext

# Import the module
from agent_builder_agentic_mcp.server._agent_instance_tools import (
    get_agent_instance,
    invoke_agent,
    list_agent_instances,
    stop_agent,
    update_agent_instance,
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

    mock_get_context = mock.MagicMock()
    mock_get_context.return_value = AgenticRequestContext(
        job_id="test-job-id",
        workspace_id="test-workspace-id",
        agent_instance_id="test-agent-id",
        authorization_token="test-token",
    )

    patcher1 = mock.patch(
        "agent_builder_agentic_mcp.server._agent_instance_tools._inject_qt_request_context",
        mock_inject,
    )
    patcher2 = mock.patch(
        "agent_builder_agentic_mcp.server._agent_instance_tools._get_request_context",
        mock_get_context,
    )
    patcher1.start()
    patcher2.start()
    yield mock_inject
    patcher1.stop()
    patcher2.stop()


@pytest.fixture
def mock_atx_client():
    """Mock the ATX client."""
    magic_mock = mock.MagicMock()
    with mock.patch(
        "agent_builder_agentic_mcp.server._agent_instance_tools.atx_agenticapi_client"
    ) as mock_atx_client:
        mock_atx_client.return_value = magic_mock
        yield mock_atx_client.return_value


@pytest.fixture
def sample_agent_instance():
    """Return a sample agent instance response."""
    return {
        "agentInstanceId": "test-agent-instance-id",
        "agentType": "TEST_AGENT",
        "agentInstanceStatus": "RUNNING",
        "agentInput": {"serializedPayload": "value"},
        "agentOutput": {"serializedPayload": "success"},
    }


@pytest.mark.anyio
async def test_invoke_agent(mock_atx_client, mock_request_context):
    """Test invoking an agent."""
    # Mock the response
    mock_atx_client.invoke_agent.return_value = {"agentInstanceId": "test-agent-instance-id"}

    # Call the function
    result = await invoke_agent(agent_id="test-agent-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.invoke_agent.assert_called_once()
    call_args = mock_atx_client.invoke_agent.call_args[1]
    assert call_args["agentId"] == "test-agent-id"
    assert "requestContext" in call_args

    # Verify the result
    assert result["agentInstanceId"] == "test-agent-instance-id"


@pytest.mark.anyio
async def test_invoke_agent_with_all_params(mock_atx_client, mock_request_context):
    """Test invoking an agent with all parameters."""
    # Mock the response
    mock_atx_client.invoke_agent.return_value = {"agentInstanceId": "test-agent-instance-id"}

    # Sample input payload as a string
    input_payload = '{"prompt": "Hello, agent!"}'

    # Call the function with all parameters
    result = await invoke_agent(
        agent_id="test-agent-id",
        agent_input=input_payload,
        agent_version="1.0",
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.invoke_agent.assert_called_once()
    call_args = mock_atx_client.invoke_agent.call_args[1]
    assert call_args["agentId"] == "test-agent-id"
    assert call_args["inputPayload"] == input_payload
    assert "idempotencyToken" in call_args  # Check that a UUID was generated
    assert call_args["agentVersion"] == "1.0"
    assert "requestContext" in call_args

    # Verify the result
    assert result["agentInstanceId"] == "test-agent-instance-id"


@pytest.mark.anyio
async def test_invoke_agent_error(mock_atx_client, mock_request_context):
    """Test error handling in invoke_agent."""
    # Set up the mock to raise an exception
    mock_atx_client.invoke_agent.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await invoke_agent(agent_id="test-agent-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.invoke_agent.assert_called_once()


@pytest.mark.anyio
async def test_get_agent_instance(mock_atx_client, mock_request_context, sample_agent_instance):
    """Test getting agent instance information."""
    # Mock the response
    mock_atx_client.get_agent_instance.return_value = sample_agent_instance

    # Call the function
    result = await get_agent_instance(agent_instance_id="test-agent-instance-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.get_agent_instance.assert_called_once()
    call_args = mock_atx_client.get_agent_instance.call_args[1]
    assert call_args["agentInstanceId"] == "test-agent-instance-id"
    assert "requestContext" in call_args

    # Verify the result
    assert result["agentInstanceId"] == "test-agent-instance-id"
    assert result["agentType"] == "TEST_AGENT"
    assert result["agentInstanceStatus"] == "RUNNING"
    assert result["agentInput"] == {"serializedPayload": "value"}
    assert result["agentOutput"] == {"serializedPayload": "success"}


@pytest.mark.anyio
async def test_get_agent_instance_error(mock_atx_client, mock_request_context):
    """Test error handling in get_agent_instance."""
    # Set up the mock to raise an exception
    mock_atx_client.get_agent_instance.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await get_agent_instance(agent_instance_id="test-agent-instance-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.get_agent_instance.assert_called_once()


@pytest.mark.anyio
async def test_update_agent_instance(mock_atx_client, mock_request_context):
    """Test updating an agent instance."""
    # Call the function
    result = await update_agent_instance(
        agent_instance_id="test-agent-instance-id", agent_instance_status="COMPLETED"
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.update_agent_instance.assert_called_once()
    call_args = mock_atx_client.update_agent_instance.call_args[1]
    assert call_args["agentInstanceId"] == "test-agent-instance-id"
    assert call_args["agentInstanceStatus"] == "COMPLETED"
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_update_agent_instance_with_all_params(mock_atx_client, mock_request_context):
    """Test updating an agent instance with all parameters."""
    # Sample agent output as a string
    agent_output = '{"result": "Task completed successfully"}'

    # Call the function with all parameters
    result = await update_agent_instance(
        agent_instance_id="test-agent-instance-id",
        agent_instance_status="COMPLETED",
        agent_instance_status_reason="Task completed",
        agent_output=agent_output,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.update_agent_instance.assert_called_once()
    call_args = mock_atx_client.update_agent_instance.call_args[1]
    assert call_args["agentInstanceId"] == "test-agent-instance-id"
    assert call_args["agentInstanceStatus"] == "COMPLETED"
    assert call_args["agentInstanceStatusReason"] == "Task completed"
    assert call_args["agentOutput"] == agent_output
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_update_agent_instance_error(mock_atx_client, mock_request_context):
    """Test error handling in update_agent_instance."""
    # Set up the mock to raise an exception
    mock_atx_client.update_agent_instance.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await update_agent_instance(
            agent_instance_id="test-agent-instance-id", agent_instance_status="COMPLETED"
        )

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.update_agent_instance.assert_called_once()


@pytest.mark.anyio
async def test_stop_agent(mock_atx_client, mock_request_context):
    """Test stopping an agent."""
    # Call the function
    result = await stop_agent(agent_instance_id="test-agent-instance-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.stop_agent.assert_called_once()
    call_args = mock_atx_client.stop_agent.call_args[1]
    assert call_args["agentInstanceId"] == "test-agent-instance-id"
    assert "requestContext" in call_args

    # Verify the result
    assert result == {}


@pytest.mark.anyio
async def test_stop_agent_error(mock_atx_client, mock_request_context):
    """Test error handling in stop_agent."""
    # Set up the mock to raise an exception
    mock_atx_client.stop_agent.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await stop_agent(agent_instance_id="test-agent-instance-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.stop_agent.assert_called_once()


@pytest.mark.anyio
async def test_list_agent_instances(mock_atx_client, mock_request_context):
    """Test listing agent instances."""
    # Sample agent instances
    agent_instances = [
        {
            "agentInstanceId": "test-agent-instance-id-1",
            "agentType": "TEST_AGENT",
            "agentInstanceStatus": "RUNNING",
        },
        {
            "agentInstanceId": "test-agent-instance-id-2",
            "agentType": "TEST_AGENT",
            "agentInstanceStatus": "COMPLETED",
        },
    ]

    # Mock the response
    mock_atx_client.list_agent_instances.return_value = {
        "agentInstanceSummaries": agent_instances,
        "nextToken": "next-page-token",
    }

    # Call the function
    result = await list_agent_instances()

    # Verify the mock was called with the right parameters
    mock_atx_client.list_agent_instances.assert_called_once()
    call_args = mock_atx_client.list_agent_instances.call_args[1]
    assert "requestContext" in call_args

    # Verify the result
    assert result["agentInstanceSummaries"] == agent_instances
    assert result["nextToken"] == "next-page-token"


@pytest.mark.anyio
async def test_list_agent_instances_with_params(mock_atx_client, mock_request_context):
    """Test listing agent instances with parameters."""
    # Sample agent instances
    agent_instances = [
        {
            "agentInstanceId": "test-agent-instance-id-1",
            "agentType": "TEST_AGENT",
            "agentInstanceStatus": "RUNNING",
        }
    ]

    # Mock the response
    mock_atx_client.list_agent_instances.return_value = {"agentInstanceSummaries": agent_instances}

    # Call the function with parameters
    result = await list_agent_instances(max_results=10, next_token="page-token")

    # Verify the mock was called with the right parameters
    mock_atx_client.list_agent_instances.assert_called_once()
    call_args = mock_atx_client.list_agent_instances.call_args[1]
    assert call_args["maxResults"] == 10
    assert call_args["nextToken"] == "page-token"
    assert "requestContext" in call_args

    # Verify the result
    assert result["agentInstanceSummaries"] == agent_instances
    assert "nextToken" not in result


@pytest.mark.anyio
async def test_list_agent_instances_error(mock_atx_client, mock_request_context):
    """Test error handling in list_agent_instances."""
    # Set up the mock to raise an exception
    mock_atx_client.list_agent_instances.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await list_agent_instances()

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.list_agent_instances.assert_called_once()
