"""
MCP client implementation.

This module provides a client for interacting with MCP servers.
"""

import logging
import typing
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from agent_builder_mcp_client.datamodels import McpToolRepr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AsyncMCPClient:
    """Client for interacting with MCP servers."""

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()
        self.tools: typing.List[McpToolRepr] = []  # Store tools for easy access
        self.prompts = []  # Store prompts for easy access

    async def connect_via_sse(
        self,
        server_url: str,
        headers: dict[str, typing.Any] | None = None,
        timeout: float = 5,
        sse_read_timeout: float = 300,
    ) -> None:
        logger.info(f"Connecting to remote MCP server at {server_url}...")

        # Connect to the remote server via SSE
        sse_transport = await self._exit_stack.enter_async_context(
            sse_client(
                url=server_url,
                headers=headers,
                timeout=timeout,
                sse_read_timeout=sse_read_timeout,
            )
        )

        # The sse_client returns a tuple of (read_func, write_func)
        stdio, write = sse_transport

        # Create a session using the SSE transport
        self._session = await self._exit_stack.enter_async_context(ClientSession(stdio, write))

        await self._session.initialize()
        logger.info(f"Successfully connected to remote MCP server at {server_url}")

        # List available tools
        await self.get_tools()
        logger.info(f"Connected to server with tools: {self.tools}")

    async def connect_via_stdio(
        self,
        command: str,
        args: typing.Optional[list[str]] = None,
        env: typing.Optional[dict[str, str]] = None,
        working_directory: str | Path | None = None,
    ) -> None:
        """

        Args:
            command: The executable to run to start the server
            args: Command line arguments to pass to the executable
            env: The environment to use when spawning the process. If not specified, the result of get_default_environment() will be used
            working_directory: The working directory to use when spawning the process

        Returns:

        """
        server_params = StdioServerParameters(
            command=command, args=args or list(), env=env, cwd=working_directory
        )

        stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(ClientSession(stdio, write))

        await self._session.initialize()

        # List available tools
        await self.get_tools()
        logger.info(f"Connected to server with tools: {self.tools}")

    async def call_tool(self, mcp_tool: typing.Union[McpToolRepr, str], **kwargs) -> CallToolResult:
        """
        Call a tool on the MCP server.

        Args:
            mcp_tool: Name of the tool to call
            **kwargs: Arguments to pass to the tool

        Returns:
            The result of the tool call
        """
        if not self._session:
            raise RuntimeError("Client is not connected to an MCP server")
        tool_name = mcp_tool.name if isinstance(mcp_tool, McpToolRepr) else mcp_tool
        logger.info(f"Invoking MCP tool: {tool_name}")

        try:
            response = await self._session.call_tool(tool_name, arguments=kwargs)
            logger.info(f"Tool execution successful with {response}")
            # TODO: represent response in package owned data class
            return response
        except Exception:
            logger.error(f"Failed to invoke MCP tool {tool_name}")
            raise

    async def get_tools(self) -> typing.List[McpToolRepr]:
        """
        Get tool schemas from MCP server in Bedrock's expected format.

        Returns:
            List of tool schemas

        Raises:
            RuntimeError: If the client is not connected to an MCP server
        """
        if self._session is None:
            raise RuntimeError("Client is not connected to an MCP server")
        logger.info("Listing tools from MCP server")
        response = await self._session.list_tools()

        tools = []
        for tool in response.tools:
            tools.append(
                McpToolRepr(
                    name=tool.name, description=tool.description, input_schema=tool.inputSchema
                )
            )

        self.tools = tools
        logger.info(f"Listed {len(self.tools)} tools from MCP server")
        return self.tools

    async def close(self) -> None:
        """Close the connection to the MCP server."""
        if self._exit_stack:
            logger.info("Closing connection to MCP server")
            await self._exit_stack.aclose()
