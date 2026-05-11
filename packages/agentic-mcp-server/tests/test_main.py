# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for main module."""

import argparse
from unittest import mock

import pytest
from agent_builder_agentic_mcp import main
from agent_builder_agentic_mcp.server._auth_handler import AuthTokenError


def test_non_empty_argparse_type_valid():
    """Test _non_empty_argparse_type function with valid input."""
    result = main._non_empty_argparse_type("valid-string")
    assert result == "valid-string"


def test_non_empty_argparse_type_empty():
    """Test _non_empty_argparse_type function with empty string."""
    with pytest.raises(argparse.ArgumentTypeError) as excinfo:
        main._non_empty_argparse_type("")
    assert "cannot be empty" in str(excinfo.value)


def test_non_empty_argparse_type_whitespace():
    """Test _non_empty_argparse_type function with whitespace-only string."""
    with pytest.raises(argparse.ArgumentTypeError) as excinfo:
        main._non_empty_argparse_type("   ")
    assert "cannot be empty" in str(excinfo.value)


def test_main_with_stdio_transport():
    """Test main function with stdio transport."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.argparse.ArgumentParser.parse_args"
    ) as mock_parse_args, mock.patch(
        "agent_builder_agentic_mcp.main.env_var.export_agent_instance_metadata"
    ) as mock_export, mock.patch(
        "agent_builder_agentic_mcp.main.verify_initialization"
    ) as mock_verify, mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token_refresher"
    ) as mock_refresher, mock.patch(
        "agent_builder_agentic_mcp.main.mcp.run"
    ) as mock_run:

        # Setup mock arguments
        mock_args = argparse.Namespace(
            transport="stdio",
            host="127.0.0.1",
            port=5002,
            workspaceId="test-workspace",
            jobId="test-job",
            agentInstanceId="test-agent",
            agenticApiEndpoint="https://test-endpoint.aws.dev",
            region="us-east-1",
            refreshToken=False,
            authTokenFile=None,
        )
        mock_parse_args.return_value = mock_args

        # Call the function
        main.main()

        # Verify the expected calls
        mock_export.assert_called_once_with(mock_args)
        mock_verify.assert_called_once()
        mock_refresher.assert_not_called()  # Should not be called when refreshToken=False
        mock_run.assert_called_once_with(transport="stdio")


def test_main_with_sse_transport():
    """Test main function with sse transport."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.argparse.ArgumentParser.parse_args"
    ) as mock_parse_args, mock.patch(
        "agent_builder_agentic_mcp.main.env_var.export_agent_instance_metadata"
    ) as mock_export, mock.patch(
        "agent_builder_agentic_mcp.main.verify_initialization"
    ) as mock_verify, mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token_refresher"
    ) as mock_refresher, mock.patch(
        "agent_builder_agentic_mcp.main.env_var.load"
    ) as mock_load, mock.patch(
        "agent_builder_agentic_mcp.main.mcp.run"
    ) as mock_run:

        # Setup mock arguments
        mock_args = argparse.Namespace(
            transport="sse",
            host="127.0.0.1",
            port=5002,
            workspaceId="test-workspace",
            jobId="test-job",
            agentInstanceId="test-agent",
            agenticApiEndpoint="https://test-endpoint.aws.dev",
            region="us-east-1",
            refreshToken=False,
            authTokenFile=None,
        )
        mock_parse_args.return_value = mock_args

        # Call the function
        main.main()

        # Verify the expected calls
        mock_export.assert_called_once_with(mock_args)
        mock_verify.assert_called_once()
        mock_refresher.assert_not_called()  # Should not be called when refreshToken=False
        mock_load.assert_called_once_with(sse_host_override="127.0.0.1", sse_port_override=5002)
        mock_run.assert_called_once_with(transport="sse")


def test_main_with_refresh_token():
    """Test main function with refreshToken=True."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.argparse.ArgumentParser.parse_args"
    ) as mock_parse_args, mock.patch(
        "agent_builder_agentic_mcp.main.env_var.export_agent_instance_metadata"
    ) as mock_export, mock.patch(
        "agent_builder_agentic_mcp.main.verify_initialization"
    ) as mock_verify, mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token_refresher"
    ) as mock_refresher, mock.patch(
        "agent_builder_agentic_mcp.main.mcp.run"
    ) as mock_run:

        # Setup mock arguments
        mock_args = argparse.Namespace(
            transport="stdio",
            host="127.0.0.1",
            port=5002,
            workspaceId="test-workspace",
            jobId="test-job",
            agentInstanceId="test-agent",
            agenticApiEndpoint="https://test-endpoint.aws.dev",
            region="us-east-1",
            refreshToken=True,
            authTokenFile=None,
        )
        mock_parse_args.return_value = mock_args

        # Call the function
        main.main()

        # Verify the expected calls
        mock_export.assert_called_once_with(mock_args)
        mock_verify.assert_called_once()
        mock_refresher.assert_called_once()  # Should be called when refreshToken=True
        mock_run.assert_called_once_with(transport="stdio")


def test_main_without_refresh_token():
    """Test main function with refreshToken=False."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.argparse.ArgumentParser.parse_args"
    ) as mock_parse_args, mock.patch(
        "agent_builder_agentic_mcp.main.env_var.export_agent_instance_metadata"
    ) as mock_export, mock.patch(
        "agent_builder_agentic_mcp.main.verify_initialization"
    ) as mock_verify, mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token_refresher"
    ) as mock_refresher, mock.patch(
        "agent_builder_agentic_mcp.main.mcp.run"
    ) as mock_run:

        # Setup mock arguments
        mock_args = argparse.Namespace(
            transport="stdio",
            host="127.0.0.1",
            port=5002,
            workspaceId="test-workspace",
            jobId="test-job",
            agentInstanceId="test-agent",
            agenticApiEndpoint="https://test-endpoint.aws.dev",
            region="us-east-1",
            refreshToken=False,
            authTokenFile=None,
        )
        mock_parse_args.return_value = mock_args

        # Call the function
        main.main()

        # Verify the expected calls
        mock_export.assert_called_once_with(mock_args)
        mock_verify.assert_called_once()
        mock_refresher.assert_not_called()  # Should not be called when refreshToken=False
        mock_run.assert_called_once_with(transport="stdio")


def test_verify_initialization_success():
    """Test verify_initialization function when successful."""
    with mock.patch("agent_builder_agentic_mcp.main.get_auth_token") as mock_get_token, mock.patch(
        "agent_builder_agentic_mcp.main.logger"
    ) as mock_logger:
        # Call the function
        main.verify_initialization()

        # Verify the expected calls
        mock_get_token.assert_called_once()
        mock_logger.info.assert_called_once_with(
            "Initialization verification successful: Auth token is readable"
        )


def test_verify_initialization_auth_token_error():
    """Test verify_initialization function when AuthTokenError is raised."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token",
        side_effect=AuthTokenError("Test auth error"),
    ) as mock_get_token, mock.patch("agent_builder_agentic_mcp.main.sys.exit") as mock_exit:
        # Call the function
        main.verify_initialization()

        # Verify the expected calls
        mock_get_token.assert_called_once()
        mock_exit.assert_called_once_with(
            "Initialization failed due to auth token error: Test auth error"
        )


def test_verify_initialization_unexpected_error():
    """Test verify_initialization function when an unexpected error is raised."""
    with mock.patch(
        "agent_builder_agentic_mcp.main.get_auth_token",
        side_effect=ValueError("Test unexpected error"),
    ) as mock_get_token, mock.patch("agent_builder_agentic_mcp.main.sys.exit") as mock_exit:
        # Call the function
        main.verify_initialization()

        # Verify the expected calls
        mock_get_token.assert_called_once()
        mock_exit.assert_called_once_with(
            "Unexpected error during initialization verification: Test unexpected error"
        )
