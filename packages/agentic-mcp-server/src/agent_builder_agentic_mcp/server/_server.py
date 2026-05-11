# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging

from mcp.server.fastmcp import FastMCP

# Configure logging
logger = logging.getLogger(__name__)

# Create the FastMCP server instance
mcp = FastMCP("atx-agentic-mcp-server")
