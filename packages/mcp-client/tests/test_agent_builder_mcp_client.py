# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for TransformAgentBuilderMCPPythonClient module."""


def test_agent_builder_mcp_client_importable():
    """Test agent_builder_mcp_client is importable."""
    import agent_builder_mcp_client  # noqa: F401


def test_async_mcp_client_importable():
    """Test agent_builder_mcp_client is importable."""
    from agent_builder_mcp_client import AsyncMCPClient, McpToolRepr  # noqa: F401
