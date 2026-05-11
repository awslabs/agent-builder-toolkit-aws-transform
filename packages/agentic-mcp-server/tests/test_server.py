# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for server modules."""

from agent_builder_agentic_mcp.server import _server


def test_server_initialization():
    """Test that the server is initialized with the correct name."""
    assert _server.mcp.name == "atx-agentic-mcp-server"
