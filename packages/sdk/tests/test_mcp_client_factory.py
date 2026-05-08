# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for MCPClientFactory."""

from unittest.mock import Mock, patch

import pytest
from strands.tools.mcp import MCPClient

from agent_builder_sdk.mcp_client_factory import MCPClientFactory


def test_setup_ab_mcp_client_success():
    """Test successful MCP client setup."""
    with patch("agent_builder_sdk.mcp_client_factory.MCPClient") as mock_mcp_client:
        mcp_args = {
            "binaryLocation": "/path/to/binary",
            "workspaceId": "test-workspace",
            "jobId": "test-job",
        }

        mock_client_instance = Mock(spec=MCPClient)
        mock_mcp_client.return_value = mock_client_instance

        result = MCPClientFactory.setup_ab_mcp_client(mcp_args)

        mock_mcp_client.assert_called_once()
        assert result == mock_client_instance


def test_setup_ab_mcp_client_no_args():
    """Test MCP client setup with no additional args."""
    with patch("agent_builder_sdk.mcp_client_factory.MCPClient") as mock_mcp_client:
        mcp_args = {"binaryLocation": "/path/to/binary"}

        mock_client_instance = Mock(spec=MCPClient)
        mock_mcp_client.return_value = mock_client_instance

        result = MCPClientFactory.setup_ab_mcp_client(mcp_args)

        mock_mcp_client.assert_called_once()
        assert result == mock_client_instance


def test_setup_ab_mcp_client_failure():
    """Test MCP client setup failure."""
    with patch(
        "agent_builder_sdk.mcp_client_factory.MCPClient",
        side_effect=Exception("Connection failed"),
    ):
        mcp_args = {"binaryLocation": "/path/to/binary"}

        with pytest.raises(Exception, match="Connection failed"):
            MCPClientFactory.setup_ab_mcp_client(mcp_args)
