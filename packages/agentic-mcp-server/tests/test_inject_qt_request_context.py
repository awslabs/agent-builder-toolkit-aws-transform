# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for _inject_qt_request_context module."""

import os
from unittest import mock

from agent_builder_agentic_mcp import env_var
from agent_builder_agentic_mcp.server import _inject_qt_request_context


def test_get_request_context():
    """Test _get_request_context function."""
    # Setup mock environment variables
    mock_env = {
        env_var.ENV_KEY_QT_JOB_ID: "test-job-id",
        env_var.ENV_KEY_QT_WORKSPACE_ID: "test-workspace-id",
        env_var.ENV_KEY_QT_AGENT_INSTANCE_ID: "test-agent-instance-id",
    }

    with mock.patch.dict(os.environ, mock_env, clear=True):
        # Mock the get_auth_token function
        with mock.patch(
            "agent_builder_agentic_mcp.server._inject_qt_request_context.get_auth_token",
            return_value="test-auth-token",
        ):
            # Call the function
            result = _inject_qt_request_context._get_request_context().to_dict()

            # Verify the result
            assert result["jobMetadata"]["jobId"] == "test-job-id"
            assert result["jobMetadata"]["workspaceId"] == "test-workspace-id"
            assert result["agentInstanceId"] == "test-agent-instance-id"
            assert result["authorizationToken"] == "test-auth-token"


def test_inject_qt_request_context_with_existing_context():
    """Test _inject_qt_request_context function with existing context."""
    # Setup input kwargs with existing requestContext
    kwargs = {"requestContext": {"existing": "context"}, "otherParam": "value"}

    # Call the function
    result = _inject_qt_request_context._inject_qt_request_context(kwargs)

    # Verify the result is unchanged
    assert result == kwargs
    assert result["requestContext"] == {"existing": "context"}


def test_inject_qt_request_context_without_existing_context():
    """Test _inject_qt_request_context function without existing context."""
    # Setup mock environment variables
    mock_env = {
        env_var.ENV_KEY_QT_JOB_ID: "test-job-id",
        env_var.ENV_KEY_QT_WORKSPACE_ID: "test-workspace-id",
        env_var.ENV_KEY_QT_AGENT_INSTANCE_ID: "test-agent-instance-id",
    }

    with mock.patch.dict(os.environ, mock_env, clear=True):
        # Setup input kwargs without requestContext
        kwargs = {"otherParam": "value"}

        # Mock the get_auth_token function
        with mock.patch(
            "agent_builder_agentic_mcp.server._inject_qt_request_context.get_auth_token",
            return_value="test-auth-token",
        ):
            # Call the function
            with mock.patch("logging.info") as mock_logging:
                result = _inject_qt_request_context._inject_qt_request_context(kwargs)

            # Verify the result has the expected requestContext
            assert result["otherParam"] == "value"
            assert result["requestContext"]["jobMetadata"]["jobId"] == "test-job-id"
            assert result["requestContext"]["jobMetadata"]["workspaceId"] == "test-workspace-id"
            assert result["requestContext"]["agentInstanceId"] == "test-agent-instance-id"
            assert result["requestContext"]["authorizationToken"] == "test-auth-token"
            mock_logging.assert_called_once()
