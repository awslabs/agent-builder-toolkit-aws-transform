"""Factory for creating MCP clients."""

import logging
import os
from typing import Dict

from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


class MCPClientFactory:
    """Factory for creating and configuring MCP clients."""

    @staticmethod
    def setup_eg_mcp_client(mcp_args: Dict[str, str]) -> MCPClient:
        """Create and configure an EG MCP client using Strands framework."""
        try:
            command_args = [
                item
                for key, value in mcp_args.items()
                for item in [f"--{key}", str(value)]
                if key != "binaryLocation"
            ]

            logger.info("Creating Strands MCP client")
            binary_location = mcp_args["binaryLocation"]
            logger.info(f"MCP command: {binary_location}, args: {command_args}")

            mcp_client = MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(
                        command=binary_location, args=command_args, env=os.environ.copy()
                    )
                )
            )

            return mcp_client
        except Exception as e:
            logger.exception("Failed to create MCP client")
            raise e
