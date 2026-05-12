# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for env_var module."""

import argparse
import os
from unittest import mock

from agent_builder_agentic_mcp import env_var


def test_load_without_overrides():
    """Test load function without any overrides."""
    with mock.patch("agent_builder_agentic_mcp.env_var.load_dotenv") as mock_load_dotenv:
        env_var.load()
        mock_load_dotenv.assert_called_once()


def test_load_with_host_override():
    """Test load function with host override."""
    with mock.patch("agent_builder_agentic_mcp.env_var.load_dotenv"), mock.patch.dict(
        os.environ, {env_var.ENV_VAR_FASTMCP_HOST: "original_host"}, clear=True
    ):
        env_var.load(sse_host_override="new_host")
        assert os.environ[env_var.ENV_VAR_FASTMCP_HOST] == "new_host"


def test_load_with_port_override():
    """Test load function with port override."""
    with mock.patch("agent_builder_agentic_mcp.env_var.load_dotenv"), mock.patch.dict(
        os.environ, {env_var.ENV_VAR_FASTMCP_PORT: "8000"}, clear=True
    ):
        env_var.load(sse_port_override=9000)
        assert os.environ[env_var.ENV_VAR_FASTMCP_PORT] == "9000"


def test_export_agent_instance_metadata():
    """Test export_agent_instance_metadata function."""
    args = argparse.Namespace(
        workspaceId="test-workspace",
        jobId="test-job",
        agentInstanceId="test-agent",
        agenticApiEndpoint="https://test-endpoint.aws.dev",
        region="us-east-1",
    )

    with mock.patch.dict(os.environ, {}, clear=True):
        # First test that basic environment variables are set correctly
        with mock.patch("pathlib.Path.exists", return_value=True):
            with mock.patch("agent_builder_agentic_mcp.env_var.logger.info"):
                env_var.export_agent_instance_metadata(args)

                assert os.environ[env_var.ENV_KEY_QT_WORKSPACE_ID] == "test-workspace"
                assert os.environ[env_var.ENV_KEY_QT_JOB_ID] == "test-job"
                assert os.environ[env_var.ENV_KEY_QT_AGENT_INSTANCE_ID] == "test-agent"
                assert os.environ[env_var.ENV_KEY_AWS_REGION] == "us-east-1"
                assert (
                    os.environ[env_var.ENV_KEY_QT_AGENTIC_API_ENDPOINT]
                    == "https://test-endpoint.aws.dev"
                )
                assert env_var.ENV_KEY_QT_AUTH_TOKEN_FILE in os.environ

    # Test the file not found case
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("pathlib.Path.exists", return_value=False):
            try:
                env_var.export_agent_instance_metadata(args)
                assert False, "Should have raised FileNotFoundError"
            except FileNotFoundError:
                # This is expected, so the test passes
                pass


def test_export_agent_instance_metadata_when_region_not_specified_should_use_env_var():
    """Test export_agent_instance_metadata uses AWS_REGION env var when region arg is absent."""
    args = argparse.Namespace(
        workspaceId="test-workspace",
        jobId="test-job",
        agentInstanceId="test-agent",
        agenticApiEndpoint="https://test-endpoint.aws.dev",
    )

    with mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True):
        with mock.patch("pathlib.Path.exists", return_value=True):
            env_var.export_agent_instance_metadata(args)

            assert os.environ[env_var.ENV_KEY_QT_WORKSPACE_ID] == "test-workspace"
            assert os.environ[env_var.ENV_KEY_QT_JOB_ID] == "test-job"
            assert os.environ[env_var.ENV_KEY_QT_AGENT_INSTANCE_ID] == "test-agent"
            assert os.environ[env_var.ENV_KEY_AWS_REGION] == "us-west-2"
            assert (
                os.environ[env_var.ENV_KEY_QT_AGENTIC_API_ENDPOINT]
                == "https://test-endpoint.aws.dev"
            )
            assert env_var.ENV_KEY_QT_AUTH_TOKEN_FILE in os.environ
