"""Tests for the Tool class."""

import json
from unittest.mock import MagicMock

import pytest

from agent_builder_sdk.tool import Tool


def test_tool_initialization_basic():
    """Test that the Tool class can be initialized with basic parameters."""
    # Arrange
    name = "test_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "Test tool description"

    # Act
    tool = Tool(name=name, func=mock_func, description=description)

    # Assert
    assert tool.name == name
    assert tool.func == mock_func
    assert tool.description == description
    assert tool.is_mcp_tool is False
    assert tool.input_schema == {
        "type": "object",
        "properties": {"input": {"type": "string", "description": "Input for the tool"}},
        "required": ["input"],
    }


def test_tool_initialization_with_input_schema():
    """Test that the Tool class can be initialized with a custom input schema."""
    # Arrange
    name = "test_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "Test tool description"
    input_schema = {
        "type": "object",
        "properties": {"param1": {"type": "string"}, "param2": {"type": "number"}},
        "required": ["param1"],
    }

    # Act
    tool = Tool(name=name, func=mock_func, description=description, input_schema=input_schema)

    # Assert
    assert tool.name == name
    assert tool.func == mock_func
    assert tool.description == description
    assert tool.input_schema == input_schema


def test_tool_initialization_with_special_schema():
    """Test that the Tool class can be initialized with a special schema-less tool definition."""
    # Arrange
    name = "special_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "Special tool description"
    special_schema = {
        "type": "computer",
        "name": "special_tool",
        "description": "Special tool description",
    }

    # Act
    tool = Tool(
        name=name,
        func=mock_func,
        description=description,
        special_schema_less_tool_definition=special_schema,
    )

    # Assert
    assert tool.name == name
    assert tool.func == mock_func
    assert tool.description == description
    assert tool.special_schema_less_tool_definition == special_schema


def test_tool_initialization_as_mcp_tool():
    """Test that the Tool class can be initialized as an MCP tool."""
    # Arrange
    name = "mcp_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "MCP tool description"

    # Act
    tool = Tool(name=name, func=mock_func, description=description, is_mcp_tool=True)

    # Assert
    assert tool.name == name
    assert tool.func == mock_func
    assert tool.description == description
    assert tool.is_mcp_tool is True


@pytest.mark.anyio
async def test_tool_call_with_dict_input():
    """Test that the Tool can be called with a dictionary input."""
    # Arrange
    mock_func = MagicMock(return_value={"content": "Tool result"})
    tool = Tool(name="test_tool", func=mock_func)
    input_data = {"param1": "value1", "param2": "value2"}

    # Act
    result = await tool(input_data)

    # Assert
    mock_func.assert_called_once_with(input_data)
    assert result == {"content": "Tool result"}


@pytest.mark.anyio
async def test_tool_call_with_string_input():
    """Test that the Tool can be called with a string input."""
    # Arrange
    mock_func = MagicMock(return_value={"content": "Tool result"})
    tool = Tool(name="test_tool", func=mock_func)
    input_data = "test input"

    # Act
    result = await tool(input_data)

    # Assert
    mock_func.assert_called_once_with({"input": "test input"})
    assert result == {"content": "Tool result"}


@pytest.mark.anyio
async def test_tool_call_with_json_string_input():
    """Test that the Tool can parse a JSON string input."""
    # Arrange
    mock_func = MagicMock(return_value={"content": "Tool result"})
    tool = Tool(name="test_tool", func=mock_func)
    json_input = '{"param1": "value1", "param2": "value2"}'
    input_data = {"input": json_input}

    # Act
    result = await tool(input_data)

    # Assert
    # The tool should have parsed the JSON string and passed the parsed object to the function
    mock_func.assert_called_once_with(json.loads(json_input))
    assert result == {"content": "Tool result"}


@pytest.mark.anyio
async def test_tool_call_with_invalid_json_string_input():
    """Test that the Tool handles invalid JSON string input gracefully."""
    # Arrange
    mock_func = MagicMock(return_value={"content": "Tool result"})
    tool = Tool(name="test_tool", func=mock_func)
    invalid_json = '{"param1": "value1", "param2": value2}'  # Missing quotes around value2
    input_data = {"input": invalid_json}

    # Act
    result = await tool(input_data)

    # Assert
    # The tool should pass the original input data since the JSON is invalid
    mock_func.assert_called_once_with(input_data)
    assert result == {"content": "Tool result"}


@pytest.mark.anyio
async def test_tool_call_with_async_function():
    """Test that the Tool can call an async function."""

    # Arrange
    async def mock_async_func(input_data):
        return {"content": "Async tool result"}

    tool = Tool(name="async_tool", func=mock_async_func)
    input_data = {"param": "value"}

    # Act
    result = await tool(input_data)

    # Assert
    assert result == {"content": "Async tool result"}


def test_tool_to_dict_normal():
    """Test that to_dict returns the correct dictionary for a normal tool."""
    # Arrange
    name = "test_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "Test tool description"
    input_schema = {
        "type": "object",
        "properties": {"param1": {"type": "string"}, "param2": {"type": "number"}},
    }

    tool = Tool(name=name, func=mock_func, description=description, input_schema=input_schema)

    # Act
    result = tool.to_dict()

    # Assert
    assert result == {"name": name, "description": description, "input_schema": input_schema}


def test_tool_to_dict_special():
    """Test that to_dict returns the special schema for a special tool."""
    # Arrange
    name = "special_tool"

    def mock_func(x):
        return {"content": "Tool result"}

    description = "Special tool description"
    special_schema = {
        "type": "computer",
        "name": "special_tool",
        "description": "Special tool description",
    }

    tool = Tool(
        name=name,
        func=mock_func,
        description=description,
        special_schema_less_tool_definition=special_schema,
    )

    # Act
    result = tool.to_dict()

    # Assert
    assert result == special_schema
