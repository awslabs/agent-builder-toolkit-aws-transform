# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Core modules for the MCP server.

This package provides the core functionality for the MCP server.
"""

# isort: skip_file
# First import the server to make mcp available
from agent_builder_agentic_mcp.server._server import mcp

# These imports are needed to register functions via decorators
# even though they appear unused to static analysis
from agent_builder_agentic_mcp.server._agent_instance_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._hitl_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._job_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._message_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._artifact_store_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._advanced_tools import *  # noqa: F401, F403
from agent_builder_agentic_mcp.server._kb_tools import *  # noqa: F401, F403


__all__ = ["mcp"]
