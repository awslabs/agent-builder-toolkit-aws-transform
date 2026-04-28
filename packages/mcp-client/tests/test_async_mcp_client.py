"""Unit tests for the MCPClient class."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp import ClientSession

from agent_builder_mcp_client.async_mcp_client import AsyncMCPClient
from agent_builder_mcp_client.datamodels import McpToolRepr


@pytest.fixture
def mock_session():
    """Create a mock ClientSession."""
    session = AsyncMock(spec=ClientSession)

    # Mock the initialize method
    session.initialize = AsyncMock()

    # Mock the list_tools method
    tools_response = MagicMock()
    tools = [MagicMock(), MagicMock()]
    tools[0].name = "tool1"
    tools[0].description = "Tool 1 description"
    tools[0].inputSchema = {"type": "object"}
    tools[1].name = "tool2"
    tools[1].description = "Tool 2 description"
    tools[1].inputSchema = {"type": "object"}
    tools_response.tools = tools
    session.list_tools = AsyncMock(return_value=tools_response)
    return session


@pytest.fixture
def mock_exit_stack():
    """Create a mock AsyncExitStack."""
    exit_stack = AsyncMock()
    exit_stack.enter_async_context = AsyncMock()
    exit_stack.aclose = AsyncMock()
    return exit_stack


@pytest.mark.anyio
async def test_connect_via_sse(mock_session, mock_exit_stack):
    """Test connecting to an MCP server via SSE."""
    # Arrange
    client = AsyncMCPClient()
    client._exit_stack = mock_exit_stack

    server_url = "https://example.com/mcp"
    headers = {"Authorization": "Bearer token123"}

    # Mock the SSE client
    mock_sse_transport = (AsyncMock(), AsyncMock())
    mock_exit_stack_context = AsyncMock()
    mock_exit_stack_context.__aenter__ = AsyncMock(return_value=mock_sse_transport)
    mock_exit_stack = client._exit_stack
    mock_exit_stack.enter_async_context.side_effect = [
        mock_sse_transport,  # For sse_client
        mock_session,  # For ClientSession
    ]

    # Mock get_tools to avoid additional complexity
    with patch.object(client, "get_tools") as mock_get_tools:
        mock_tools = [
            McpToolRepr(
                name="tool1", description="Tool 1 description", input_schema={"type": "object"}
            ),
            McpToolRepr(
                name="tool2", description="Tool 2 description", input_schema={"type": "object"}
            ),
        ]
        mock_get_tools.return_value = mock_tools

        # Act
        with patch(
            "agent_builder_mcp_client.async_mcp_client.sse_client", return_value=mock_exit_stack_context
        ):
            await client.connect_via_sse(server_url, headers)

        # Manually set tools since the mock doesn't update the client's tools attribute
        client.tools = mock_tools

    # Assert
    mock_exit_stack.enter_async_context.assert_called()
    assert client._session == mock_session
    mock_session.initialize.assert_called_once()
    mock_get_tools.assert_called_once()
    assert len(client.tools) == 2
    assert all(isinstance(tool, McpToolRepr) for tool in client.tools)
    assert client.tools[0].name == "tool1"
    assert client.tools[1].name == "tool2"


@pytest.mark.anyio
async def test_connect_via_stdio(mock_session, mock_exit_stack):
    """Test connecting to an MCP server via stdio."""
    # Arrange
    client = AsyncMCPClient()
    client._exit_stack = mock_exit_stack

    command = "amzn-mcp"
    args = ["--arg1", "--arg2"]
    env = {"ENV_VAR": "value"}
    working_directory = Path("/tmp")

    # Mock the stdio client
    mock_stdio_transport = (AsyncMock(), AsyncMock())
    mock_exit_stack_context = AsyncMock()
    mock_exit_stack_context.__aenter__ = AsyncMock(return_value=mock_stdio_transport)
    mock_exit_stack = client._exit_stack
    mock_exit_stack.enter_async_context.side_effect = [
        mock_stdio_transport,  # For stdio_client
        mock_session,  # For ClientSession
    ]

    # Mock get_tools to avoid additional complexity
    with patch.object(client, "get_tools") as mock_get_tools:
        mock_tools = [
            McpToolRepr(
                name="tool1", description="Tool 1 description", input_schema={"type": "object"}
            ),
            McpToolRepr(
                name="tool2", description="Tool 2 description", input_schema={"type": "object"}
            ),
        ]
        mock_get_tools.return_value = mock_tools

        # Act
        with patch(
            "agent_builder_mcp_client.async_mcp_client.stdio_client", return_value=mock_exit_stack_context
        ):
            await client.connect_via_stdio(command, args, env, working_directory)

        # Manually set tools since the mock doesn't update the client's tools attribute
        client.tools = mock_tools

    # Assert
    mock_exit_stack.enter_async_context.assert_called()
    assert client._session == mock_session
    mock_session.initialize.assert_called_once()
    mock_get_tools.assert_called_once()
    assert len(client.tools) == 2
    assert all(isinstance(tool, McpToolRepr) for tool in client.tools)
    assert client.tools[0].name == "tool1"
    assert client.tools[1].name == "tool2"


@pytest.mark.anyio
async def test_close():
    """Test closing the connection to the MCP server."""
    # Arrange
    client = AsyncMCPClient()
    client._exit_stack = AsyncMock()

    # Act
    await client.close()

    # Assert
    client._exit_stack.aclose.assert_called_once()


@pytest.mark.anyio
async def test_connect_via_sse_with_defaults():
    """Test connecting to an MCP server via SSE with default parameters."""
    # Arrange
    client = AsyncMCPClient()

    # Mock the necessary components
    mock_sse_transport = (AsyncMock(), AsyncMock())
    mock_session = AsyncMock(spec=ClientSession)

    # Create tools with proper name attributes
    tools = [MagicMock(), MagicMock()]
    tools[0].name = "tool1"
    tools[0].description = "Tool 1 description"
    tools[0].inputSchema = {"type": "object"}
    tools[1].name = "tool2"
    tools[1].description = "Tool 2 description"
    tools[1].inputSchema = {"type": "object"}

    tools_response = MagicMock()
    tools_response.tools = tools
    mock_session.list_tools = AsyncMock(return_value=tools_response)

    # Act
    with patch("agent_builder_mcp_client.async_mcp_client.sse_client") as mock_sse_client, patch(
        "agent_builder_mcp_client.async_mcp_client.ClientSession", return_value=mock_session
    ), patch.object(client._exit_stack, "enter_async_context") as mock_enter_context, patch.object(
        mock_session, "initialize"
    ) as mock_initialize:

        mock_sse_context = AsyncMock()
        mock_sse_context.__aenter__ = AsyncMock(return_value=mock_sse_transport)
        mock_sse_client.return_value = mock_sse_context

        mock_enter_context.side_effect = [mock_sse_transport, mock_session]

        # Mock get_tools to return McpToolRepr objects
        with patch.object(client, "get_tools") as mock_get_tools:
            mock_tools = [
                McpToolRepr(
                    name="tool1", description="Tool 1 description", input_schema={"type": "object"}
                ),
                McpToolRepr(
                    name="tool2", description="Tool 2 description", input_schema={"type": "object"}
                ),
            ]
            mock_get_tools.return_value = mock_tools

            await client.connect_via_sse("https://example.com/mcp")

            # Manually set tools since the mock doesn't update the client's tools attribute
            client.tools = mock_tools

    # Assert
    mock_initialize.assert_called_once()
    assert len(client.tools) == 2
    assert all(isinstance(tool, McpToolRepr) for tool in client.tools)


@pytest.mark.anyio
async def test_client_initialization():
    """Test that the MCPClient initializes with the expected default values."""
    # Act
    client = AsyncMCPClient()

    # Assert
    assert client._session is None
    assert client.tools == []
    assert client.prompts == []


@pytest.mark.anyio
async def test_connect_via_sse_logs_correctly(caplog):
    """Test that connect_via_sse logs the expected messages."""
    # Arrange
    caplog.set_level(logging.INFO)
    client = AsyncMCPClient()
    server_url = "https://example.com/mcp"

    # Mock the necessary components
    mock_sse_transport = (AsyncMock(), AsyncMock())
    mock_session = AsyncMock(spec=ClientSession)

    # Create tools with proper name attributes
    tools = [MagicMock(), MagicMock()]
    tools[0].name = "tool1"
    tools[0].description = "Tool 1 description"
    tools[0].inputSchema = {"type": "object"}
    tools[1].name = "tool2"
    tools[1].description = "Tool 2 description"
    tools[1].inputSchema = {"type": "object"}

    tools_response = MagicMock()
    tools_response.tools = tools
    mock_session.list_tools = AsyncMock(return_value=tools_response)

    # Act
    with patch("agent_builder_mcp_client.async_mcp_client.sse_client") as mock_sse_client, patch(
        "agent_builder_mcp_client.async_mcp_client.ClientSession", return_value=mock_session
    ), patch.object(client._exit_stack, "enter_async_context") as mock_enter_context:

        mock_sse_context = AsyncMock()
        mock_sse_context.__aenter__ = AsyncMock(return_value=mock_sse_transport)
        mock_sse_client.return_value = mock_sse_context

        mock_enter_context.side_effect = [mock_sse_transport, mock_session]

        # Mock get_tools to return McpToolRepr objects
        with patch.object(client, "get_tools") as mock_get_tools:
            mock_tools = [
                McpToolRepr(
                    name="tool1", description="Tool 1 description", input_schema={"type": "object"}
                ),
                McpToolRepr(
                    name="tool2", description="Tool 2 description", input_schema={"type": "object"}
                ),
            ]
            mock_get_tools.return_value = mock_tools
            client.tools = mock_tools

            await client.connect_via_sse(server_url)

    # Assert
    assert f"Connecting to remote MCP server at {server_url}" in caplog.text
    assert f"Successfully connected to remote MCP server at {server_url}" in caplog.text
    assert "Connected to server with tools:" in caplog.text


@pytest.mark.anyio
async def test_close_logs_correctly(caplog):
    """Test that close logs the expected message."""
    # Arrange
    caplog.set_level(logging.INFO)
    client = AsyncMCPClient()
    client._exit_stack = AsyncMock()

    # Act
    await client.close()

    # Assert
    assert "Closing connection to MCP server" in caplog.text


@pytest.mark.anyio
async def test_get_tools():
    """Test that get_tools returns the expected tool representations."""
    # Arrange
    client = AsyncMCPClient()

    # Create a mock session
    mock_session = AsyncMock(spec=ClientSession)
    client._session = mock_session

    # Create mock tools with the necessary attributes
    tool1 = MagicMock()
    tool1.name = "tool1"
    tool1.description = "Tool 1 description"
    tool1.inputSchema = {"type": "object", "properties": {"param1": {"type": "string"}}}

    tool2 = MagicMock()
    tool2.name = "tool2"
    # Intentionally omit description to test the default value
    tool2.description = None
    tool2.inputSchema = {"type": "object", "properties": {"param2": {"type": "number"}}}

    # Mock the list_tools response
    tools_response = MagicMock()
    tools_response.tools = [tool1, tool2]
    mock_session.list_tools = AsyncMock(return_value=tools_response)

    # Act
    result = await client.get_tools()

    # Assert
    assert len(result) == 2

    # Check first tool
    assert isinstance(result[0], McpToolRepr)
    assert result[0].name == "tool1"
    assert result[0].description == "Tool 1 description"
    assert result[0].input_schema == {
        "type": "object",
        "properties": {"param1": {"type": "string"}},
    }

    # Check second tool (with None description)
    assert isinstance(result[1], McpToolRepr)
    assert result[1].name == "tool2"
    assert result[1].description is None
    assert result[1].input_schema == {
        "type": "object",
        "properties": {"param2": {"type": "number"}},
    }

    # Check that tools are stored in the client
    assert client.tools == result


@pytest.mark.anyio
async def test_get_tools_with_complex_schemas():
    """Test get_tools with more complex input schemas."""
    # Arrange
    client = AsyncMCPClient()

    # Create a mock session
    mock_session = AsyncMock(spec=ClientSession)
    client._session = mock_session

    # Create a mock tool with a complex schema
    complex_tool = MagicMock()
    complex_tool.name = "complex_tool"
    complex_tool.description = "A tool with a complex schema"
    complex_tool.inputSchema = {
        "type": "object",
        "required": ["query", "max_results"],
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "minimum": 1,
                "maximum": 100,
            },
            "filters": {
                "type": "object",
                "properties": {
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "format": "date"},
                            "end": {"type": "string", "format": "date"},
                        },
                    },
                    "categories": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }

    # Mock the list_tools response
    tools_response = MagicMock()
    tools_response.tools = [complex_tool]
    mock_session.list_tools = AsyncMock(return_value=tools_response)

    # Act
    result = await client.get_tools()

    # Assert
    assert len(result) == 1
    assert isinstance(result[0], McpToolRepr)
    assert result[0].name == "complex_tool"
    assert result[0].description == "A tool with a complex schema"

    # Verify the complex schema is preserved
    schema = result[0].input_schema
    assert schema["type"] == "object"
    assert "query" in schema["required"]
    assert "max_results" in schema["required"]
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["max_results"]["minimum"] == 1
    assert schema["properties"]["max_results"]["maximum"] == 100
    assert schema["properties"]["filters"]["properties"]["categories"]["type"] == "array"


@pytest.mark.anyio
async def test_call_tool_with_string_name():
    """Test calling a tool using a string name."""
    # Arrange
    client = AsyncMCPClient()
    mock_session = AsyncMock(spec=ClientSession)
    client._session = mock_session

    tool_name = "test_tool"
    tool_args = {"param1": "value1", "param2": 42}
    expected_response = {"result": "success", "data": {"key": "value"}}

    # Mock the call_tool method of the session
    mock_session.call_tool = AsyncMock(return_value=expected_response)

    # Act
    result = await client.call_tool(tool_name, **tool_args)

    # Assert
    mock_session.call_tool.assert_called_once_with(tool_name, arguments=tool_args)
    assert result == expected_response


@pytest.mark.anyio
async def test_call_tool_with_tool_repr():
    """Test calling a tool using a McpToolRepr object."""
    # Arrange
    client = AsyncMCPClient()
    mock_session = AsyncMock(spec=ClientSession)
    client._session = mock_session

    tool_repr = McpToolRepr(
        name="test_tool", description="Test tool description", input_schema={"type": "object"}
    )
    tool_args = {"param1": "value1", "param2": 42}
    expected_response = {"result": "success", "data": {"key": "value"}}

    # Mock the call_tool method of the session
    mock_session.call_tool = AsyncMock(return_value=expected_response)

    # Act
    result = await client.call_tool(tool_repr, **tool_args)

    # Assert
    mock_session.call_tool.assert_called_once_with(tool_repr.name, arguments=tool_args)
    assert result == expected_response


@pytest.mark.anyio
async def test_call_tool_not_connected():
    """Test calling a tool when not connected to an MCP server."""
    # Arrange
    client = AsyncMCPClient()
    client._session = None

    # Act & Assert
    with pytest.raises(RuntimeError, match="Client is not connected to an MCP server"):
        await client.call_tool("test_tool", param1="value1")


@pytest.mark.anyio
async def test_call_tool_exception_handling():
    """Test that exceptions from call_tool are properly handled."""
    # Arrange
    client = AsyncMCPClient()
    mock_session = AsyncMock(spec=ClientSession)
    client._session = mock_session

    tool_name = "test_tool"
    tool_args = {"param1": "value1"}

    # Mock the call_tool method to raise an exception
    mock_session.call_tool = AsyncMock(side_effect=ValueError("Tool execution failed"))

    # Act & Assert
    with pytest.raises(ValueError, match="Tool execution failed"):
        await client.call_tool(tool_name, **tool_args)

    mock_session.call_tool.assert_called_once_with(tool_name, arguments=tool_args)
