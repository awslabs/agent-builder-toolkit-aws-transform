# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the message tools functionality.
"""

import os
from unittest import mock

import pytest
from agent_builder_agentic_mcp import env_var
from agent_builder_agentic_mcp.custom_types.message_types import (
    HitlSubmitterA2AMsgTarget,
    JobCreatorA2AMsgTarget,
    SpecificUserA2AMsgTarget,
)
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext
from agent_builder_agentic_mcp.server._message_tools import (
    reply_message_to_user,
    send_message_to_user,
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
        "agent_builder_agentic_mcp.server._message_tools.atx_agenticapi_client"
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


@pytest.mark.anyio
async def test_send_message_job_creator_target(mock_atx_client, mock_request_context):
    """Test sending message with job creator target."""
    mock_response = {"result": {"success": True}}
    mock_atx_client.send_message.return_value = mock_response

    target = JobCreatorA2AMsgTarget(userSelection="jobCreator")
    result = await send_message_to_user("Hello from agent!", target)

    assert result == mock_response
    mock_atx_client.send_message.assert_called_once()
    call_args = mock_atx_client.send_message.call_args[1]

    assert call_args["agentInstanceId"] == "ATX_CHAT"
    assert call_args["params"]["message"]["parts"][0]["text"] == "Hello from agent!"
    assert call_args["params"]["message"]["role"] == "agent"
    assert (
        call_args["params"]["message"]["metadata"][
            "https://aws.com/transform/ext/message-targeting/v1"
        ]["userSelection"]
        == "jobCreator"
    )
    assert (
        call_args["params"]["message"]["extensions"][0]
        == "https://aws.com/transform/ext/message-targeting/v1"
    )


@pytest.mark.anyio
async def test_send_message_hitl_submitter_target(mock_atx_client, mock_request_context):
    """Test sending message with HITL submitter target."""
    mock_response = {"result": {"success": True}}
    mock_atx_client.send_message.return_value = mock_response

    target = HitlSubmitterA2AMsgTarget(userSelection="hitlSubmitter", hitlTaskId="task-123")
    result = await send_message_to_user("HITL task completed!", target)

    assert result == mock_response
    call_args = mock_atx_client.send_message.call_args[1]

    targeting_metadata = call_args["params"]["message"]["metadata"][
        "https://aws.com/transform/ext/message-targeting/v1"
    ]
    assert targeting_metadata["userSelection"] == "hitlSubmitter"
    assert targeting_metadata["hitlTaskId"] == "task-123"
    assert (
        call_args["params"]["message"]["extensions"][0]
        == "https://aws.com/transform/ext/message-targeting/v1"
    )


@pytest.mark.anyio
async def test_send_message_specific_user_target(mock_atx_client, mock_request_context):
    """Test sending message with specific user target."""
    mock_response = {"result": {"success": True}}
    mock_atx_client.send_message.return_value = mock_response

    target = SpecificUserA2AMsgTarget(userSelection="specificUser", userId="user-456")
    result = await send_message_to_user("Direct message!", target)

    assert result == mock_response
    call_args = mock_atx_client.send_message.call_args[1]

    targeting_metadata = call_args["params"]["message"]["metadata"][
        "https://aws.com/transform/ext/message-targeting/v1"
    ]
    assert targeting_metadata["userSelection"] == "specificUser"
    assert targeting_metadata["userId"] == "user-456"
    assert (
        call_args["params"]["message"]["extensions"][0]
        == "https://aws.com/transform/ext/message-targeting/v1"
    )


@pytest.mark.anyio
async def test_send_message_exception_handling(mock_atx_client, mock_request_context):
    """Test exception handling in send_message_to_user."""
    mock_atx_client.send_message.side_effect = Exception("API Error")

    target = JobCreatorA2AMsgTarget(userSelection="jobCreator")

    with pytest.raises(Exception, match="API Error"):
        await send_message_to_user("Hello!", target)


@pytest.mark.anyio
async def test_reply_message_to_user(mock_atx_client, mock_request_context):
    """Test responding to existing chat conversation."""
    mock_response = {"result": {"success": True}}
    mock_atx_client.send_message.return_value = mock_response

    result = await reply_message_to_user("ctx-123", "Thanks for your message!")

    assert result == mock_response
    mock_atx_client.send_message.assert_called_once()
    call_args = mock_atx_client.send_message.call_args[1]

    assert call_args["agentInstanceId"] == "ATX_CHAT"
    assert call_args["params"]["message"]["contextId"] == "ctx-123"
    assert call_args["params"]["message"]["parts"][0]["text"] == "Thanks for your message!"
    assert call_args["params"]["message"]["role"] == "agent"


@pytest.mark.anyio
async def test_reply_message_exception_handling(mock_atx_client, mock_request_context):
    """Test exception handling in reply_message_to_user."""
    mock_atx_client.send_message.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        await reply_message_to_user("ctx-123", "Hello!")
