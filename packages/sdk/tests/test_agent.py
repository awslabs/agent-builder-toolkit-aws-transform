# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Agent class."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_builder_sdk.agent import Agent
from agent_builder_sdk.tool import Tool


@pytest.fixture(autouse=True)
def _fresh_event_loop():
    """Give each test a fresh event loop so closed-loop errors don't cascade."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()


@patch("agent_builder_sdk.agent.tool_use_prompts.apply_tool_use_prompts")
def test_agent_initialization_basic(mock_apply_tool_use_prompts):
    """Test that the Agent class can be initialized with basic parameters."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Configure the mock to return the original prompt without modification
    mock_apply_tool_use_prompts.return_value = system_prompt
    # Act
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)
    # Assert
    assert agent.system_prompt == system_prompt
    assert agent.model_id == bedrock_model_id
    assert agent.mcp_client is None
    assert agent.tools == []
    assert agent._messages == []
    assert agent._bedrock_runtime is not None
    # Verify that apply_tool_use_prompts was called with the correct arguments
    mock_apply_tool_use_prompts.assert_called_once_with(bedrock_model_id, system_prompt)


@patch("agent_builder_sdk.agent.tool_use_prompts.apply_tool_use_prompts")
def test_agent_initialization_with_mcp_client(mock_apply_tool_use_prompts):
    """Test that the Agent class can be initialized with an MCP client."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = MagicMock()
    # Configure the mock to return the original prompt without modification
    mock_apply_tool_use_prompts.return_value = system_prompt
    # Act
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )
    # Assert
    assert agent.system_prompt == system_prompt
    assert agent.model_id == bedrock_model_id
    assert agent.mcp_client == mock_mcp_client
    assert agent.tools == []
    assert agent._messages == []
    assert agent._bedrock_runtime is not None


@patch("agent_builder_sdk.agent.tool_use_prompts.apply_tool_use_prompts")
def test_register_tool(mock_apply_tool_use_prompts):
    """Test that a tool can be registered with the agent."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_apply_tool_use_prompts.return_value = system_prompt
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    async def mock_tool_func(input_data):
        return {"content": [{"type": "text", "text": "Tool result"}]}

    tool = Tool(
        name="test_tool",
        func=mock_tool_func,
        input_schema={"type": "object", "properties": {}},
        description="Test tool",
    )
    # Act
    agent.register_tool(tool)
    # Assert
    assert len(agent.tools) == 1
    assert agent.tools[0] == tool
    assert agent.tools[0].name == "test_tool"
    assert agent.tools[0].description == "Test tool"


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_invoke_claude(mock_create_bedrock_client):
    """Test that the invoke_claude method properly formats the request and handles the response."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create a mock bedrock client
    mock_bedrock_client = MagicMock()
    mock_create_bedrock_client.return_value = mock_bedrock_client

    # Configure the mock response
    mock_response = {"body": MagicMock()}
    mock_response["body"].read.return_value = (
        '{"role": "assistant", "content": "Hello, how can I help you?"}'
    )
    mock_bedrock_client.invoke_model.return_value = mock_response

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create test messages
    messages = [{"role": "user", "content": "Hello, Claude!"}]

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(agent.invoke_claude(messages))

    # Assert
    mock_bedrock_client.invoke_model.assert_called_once()
    call_args = mock_bedrock_client.invoke_model.call_args[1]
    assert call_args["modelId"] == bedrock_model_id

    # Parse the request body to verify it's correctly formatted
    request_body = json.loads(call_args["body"])
    assert request_body["anthropic_version"] == "bedrock-2023-05-31"
    assert request_body["max_tokens"] == 4096
    assert request_body["messages"] == messages

    # Verify the response is correctly parsed
    assert response["role"] == "assistant"
    assert response["content"] == "Hello, how can I help you?"


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_format_tools_for_claude(mock_create_bedrock_client):
    """Test that the _format_tools_for_claude method correctly formats tools for Claude."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create a mock bedrock client
    mock_bedrock_client = MagicMock()
    mock_create_bedrock_client.return_value = mock_bedrock_client

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create a mock tool
    async def mock_tool_func(input_data):
        return {"content": [{"type": "text", "text": "Tool result"}]}

    tool = Tool(
        name="test_tool",
        func=mock_tool_func,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        description="Test tool description",
    )

    # Register the tool
    agent.register_tool(tool)

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    claude_tools = loop.run_until_complete(agent._format_tools_for_claude())

    # Assert
    assert len(claude_tools) == 1
    assert claude_tools[0]["name"] == "test_tool"
    assert claude_tools[0]["description"] == "Test tool description"
    assert "input_schema" in claude_tools[0]
    assert claude_tools[0]["input_schema"]["type"] == "object"
    assert "query" in claude_tools[0]["input_schema"]["properties"]


@patch("agent_builder_sdk.agent.Agent.invoke_claude")
@patch("agent_builder_sdk.agent.Agent._format_tools_for_claude")
def test_process_simple_response(mock_format_tools, mock_invoke_claude):
    """Test that the process method correctly handles a simple response without tool calls."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)
    # Configure mocks
    mock_format_tools.return_value = []
    mock_invoke_claude.return_value = {
        "role": "assistant",
        "content": "This is a test response",
        "stop_reason": "end_turn",
    }
    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(agent.process("Hello, agent!"))
    # Assert
    mock_format_tools.assert_called_once()
    mock_invoke_claude.assert_called_once()
    assert response["role"] == "assistant"
    assert response["content"] == "This is a test response"
    assert response["stop_reason"] == "end_turn"
    assert response["tool_name_invoked"] is None


@patch("agent_builder_sdk.agent.Agent.invoke_claude")
@patch("agent_builder_sdk.agent.Agent._format_tools_for_claude")
def test_process_with_tool_call(mock_format_tools, mock_invoke_claude):
    """Test that the process method correctly handles a response with a tool call."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create a mock tool
    async def mock_tool_func(input_data):
        return {"content": [{"type": "text", "text": "Tool result"}]}

    tool = Tool(
        name="test_tool",
        func=mock_tool_func,
        input_schema={"type": "object", "properties": {}},
        description="Test tool",
    )
    # Register the tool
    agent.register_tool(tool)
    # Configure mocks
    mock_format_tools.return_value = [tool.to_dict()]
    # First response with tool call
    mock_invoke_claude.side_effect = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "test_tool", "id": "tool_1", "input": {}}],
            "stop_reason": "tool_use",
        },
        # Second response after tool call
        {
            "role": "assistant",
            "content": "I used the tool and got a result",
            "stop_reason": "end_turn",
        },
    ]
    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(agent.process("Use the test tool"))
    # Assert
    assert mock_format_tools.call_count == 1
    assert mock_invoke_claude.call_count == 2
    assert response["role"] == "assistant"
    assert response["content"] == "I used the tool and got a result"
    assert response["stop_reason"] == "end_turn"
    assert response["tool_name_invoked"] == "test_tool"


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_shutdown(mock_create_bedrock_client):
    """Test that the shutdown method properly closes the MCP client."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.shutdown())

    # Assert
    mock_mcp_client.close.assert_called_once()


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_register_mcp_tools(mock_create_bedrock_client):
    """Test that MCP tools are properly registered."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Create mock tool schemas
    mock_tool_schema1 = MagicMock()
    mock_tool_schema1.name = "mcp_tool1"
    mock_tool_schema1.description = "MCP Tool 1 Description"
    mock_tool_schema1.input_schema = {
        "type": "object",
        "properties": {"param1": {"type": "string"}},
    }

    mock_tool_schema2 = MagicMock()
    mock_tool_schema2.name = "mcp_tool2"
    mock_tool_schema2.description = None  # Test the case where description is None
    mock_tool_schema2.input_schema = {
        "type": "object",
        "properties": {"param2": {"type": "number"}},
    }

    # Configure the mock MCP client to return the tool schemas
    mock_mcp_client.get_tools.return_value = [mock_tool_schema1, mock_tool_schema2]

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.register_mcp_tools())

    # Assert
    mock_mcp_client.get_tools.assert_called_once()
    assert len(agent.tools) == 2
    assert agent.tools[0].name == "mcp_tool1"
    assert agent.tools[0].description == "MCP Tool 1 Description"
    assert agent.tools[0].is_mcp_tool is True
    assert agent.tools[1].name == "mcp_tool2"
    assert agent.tools[1].description == "MCP tool: mcp_tool2"  # Default description
    assert agent.tools[1].is_mcp_tool is True


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_register_mcp_tools_no_client(mock_create_bedrock_client):
    """Test that register_mcp_tools handles the case where no MCP client is provided."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create the agent without an MCP client
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.register_mcp_tools())

    # Assert
    assert len(agent.tools) == 0  # No tools should be registered


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_register_mcp_tools_error(mock_create_bedrock_client):
    """Test that register_mcp_tools properly handles errors."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Configure the mock MCP client to raise an exception
    mock_mcp_client.get_tools.side_effect = Exception("Failed to get tools")

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Act & Assert - The function should raise the exception
    loop = asyncio.get_event_loop()
    with patch("agent_builder_sdk.agent.logger") as mock_logger:
        try:
            loop.run_until_complete(agent.register_mcp_tools())
            assert False, "Expected an exception but none was raised"
        except Exception as e:
            assert str(e) == "Failed to get tools"
            mock_logger.error.assert_called()


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_invoke_claude_error(mock_create_bedrock_client):
    """Test that invoke_claude properly handles errors."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create a mock bedrock client that raises an exception
    mock_bedrock_client = MagicMock()
    mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock API error")
    mock_create_bedrock_client.return_value = mock_bedrock_client

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create test messages
    messages = [{"role": "user", "content": "Hello, Claude!"}]

    # Act & Assert - The function should raise the exception
    loop = asyncio.get_event_loop()
    with patch("agent_builder_sdk.agent.logger") as mock_logger:
        try:
            loop.run_until_complete(agent.invoke_claude(messages))
            assert False, "Expected an exception but none was raised"
        except Exception as e:
            assert "Bedrock API error" in str(e)
            mock_logger.error.assert_called()


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_invoke_claude_empty_messages(mock_create_bedrock_client):
    """Test that invoke_claude handles empty messages list."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Act & Assert - The function should raise a ValueError
    loop = asyncio.get_event_loop()
    with patch("agent_builder_sdk.agent.logger"):
        try:
            loop.run_until_complete(agent.invoke_claude([]))
            assert False, "Expected an exception but none was raised"
        except ValueError as e:
            assert "No messages provided" in str(e)


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_invoke_claude_with_tools(mock_create_bedrock_client):
    """Test that invoke_claude properly handles tools parameter."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create a mock bedrock client
    mock_bedrock_client = MagicMock()
    mock_response = {"body": MagicMock()}
    mock_response["body"].read.return_value = '{"role": "assistant", "content": "Hello!"}'
    mock_bedrock_client.invoke_model.return_value = mock_response
    mock_create_bedrock_client.return_value = mock_bedrock_client

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create test messages and tools
    messages = [{"role": "user", "content": "Hello!"}]
    tools = [
        {
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]

    # Act
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.invoke_claude(messages, tools))

    # Assert
    mock_bedrock_client.invoke_model.assert_called_once()
    call_args = mock_bedrock_client.invoke_model.call_args[1]
    request_body = json.loads(call_args["body"])
    assert "tools" in request_body
    assert request_body["tools"] == tools


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_invoke_claude_with_special_tools(mock_create_bedrock_client):
    """Test that invoke_claude properly handles special tools with type field."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Create a mock bedrock client
    mock_bedrock_client = MagicMock()
    mock_response = {"body": MagicMock()}
    mock_response["body"].read.return_value = '{"role": "assistant", "content": "Hello!"}'
    mock_bedrock_client.invoke_model.return_value = mock_response
    mock_create_bedrock_client.return_value = mock_bedrock_client

    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create test messages and tools with a special tool
    messages = [{"role": "user", "content": "Hello!"}]
    tools = [
        {
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {"type": "object", "properties": {}},
        },
        {"type": "computer", "name": "special_tool", "description": "A special tool"},
    ]

    # Act
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.invoke_claude(messages, tools))

    # Assert
    mock_bedrock_client.invoke_model.assert_called_once()
    call_args = mock_bedrock_client.invoke_model.call_args[1]
    request_body = json.loads(call_args["body"])
    assert "tools" in request_body
    assert request_body["tools"] == tools
    assert "anthropic_beta" in request_body
    assert request_body["anthropic_beta"] == ["computer-use-2024-10-22"]


@patch("agent_builder_sdk.agent.Agent.invoke_claude")
@patch("agent_builder_sdk.agent.Agent._format_tools_for_claude")
def test_process_with_multiple_tool_calls(mock_format_tools, mock_invoke_claude):
    """Test that the process method correctly handles multiple tool calls."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create mock tools
    async def mock_tool_func1(input_data):
        return {"content": [{"type": "text", "text": "Tool 1 result"}]}

    async def mock_tool_func2(input_data):
        return {"content": [{"type": "text", "text": "Tool 2 result"}]}

    tool1 = Tool(
        name="test_tool1",
        func=mock_tool_func1,
        input_schema={"type": "object", "properties": {}},
        description="Test tool 1",
    )

    tool2 = Tool(
        name="test_tool2",
        func=mock_tool_func2,
        input_schema={"type": "object", "properties": {}},
        description="Test tool 2",
    )

    # Register the tools
    agent.register_tool(tool1)
    agent.register_tool(tool2)

    # Configure mocks
    mock_format_tools.return_value = [tool1.to_dict(), tool2.to_dict()]

    # First response with multiple tool calls
    mock_invoke_claude.side_effect = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "test_tool1", "id": "tool_1", "input": {}},
                {"type": "tool_use", "name": "test_tool2", "id": "tool_2", "input": {}},
            ],
            "stop_reason": "tool_use",
        },
        # Second response after tool calls
        {
            "role": "assistant",
            "content": "I used both tools and got results",
            "stop_reason": "end_turn",
        },
    ]

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    with patch("agent_builder_sdk.agent.logger") as mock_logger:
        response = loop.run_until_complete(agent.process("Use both tools"))

    # Assert
    assert mock_format_tools.call_count == 1
    assert mock_invoke_claude.call_count == 2
    assert response["role"] == "assistant"
    assert response["content"] == "I used both tools and got results"
    assert response["stop_reason"] == "end_turn"
    assert response["tool_name_invoked"] == "Multiple"
    mock_logger.warning.assert_called_once()


@patch("agent_builder_sdk.agent.Agent.invoke_claude")
@patch("agent_builder_sdk.agent.Agent._format_tools_for_claude")
def test_process_tool_execution_error(mock_format_tools, mock_invoke_claude):
    """Test that the process method correctly handles tool execution errors."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Create a mock tool that raises an exception
    async def mock_tool_func(input_data):
        raise Exception("Tool execution failed")

    tool = Tool(
        name="error_tool",
        func=mock_tool_func,
        input_schema={"type": "object", "properties": {}},
        description="Error tool",
    )

    # Register the tool
    agent.register_tool(tool)

    # Configure mocks
    mock_format_tools.return_value = [tool.to_dict()]

    # Response with tool call
    mock_invoke_claude.return_value = {
        "role": "assistant",
        "content": [{"type": "tool_use", "name": "error_tool", "id": "tool_1", "input": {}}],
        "stop_reason": "tool_use",
    }

    # Act & Assert - The function should raise the exception
    loop = asyncio.get_event_loop()
    with patch("agent_builder_sdk.agent.logger") as mock_logger:
        try:
            loop.run_until_complete(agent.process("Use the error tool"))
            assert False, "Expected an exception but none was raised"
        except Exception as e:
            assert "Tool execution failed" in str(e)
            mock_logger.error.assert_called()


@patch("agent_builder_sdk.agent.Agent.process")
def test_call_method(mock_process):
    """Test that the __call__ method correctly delegates to process."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # Create the agent
    agent = Agent(system_prompt=system_prompt, bedrock_model_id=bedrock_model_id)

    # Configure mock
    mock_process.return_value = {"role": "assistant", "content": "Response from process"}

    # Act - Run the async function in a synchronous context
    loop = asyncio.get_event_loop()
    response = loop.run_until_complete(agent("Hello, agent!"))

    # Assert
    mock_process.assert_called_once_with("Hello, agent!")
    assert response == {"role": "assistant", "content": "Response from process"}


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_mcp_tool_wrapper(mock_create_bedrock_client):
    """Test that the MCP tool wrapper function works correctly."""
    # This test specifically targets the tool_wrapper function created in register_mcp_tools

    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Create mock tool response
    mock_tool_result = MagicMock()
    mock_tool_result.content = [MagicMock()]
    mock_tool_result.content[0].text = "MCP tool result"
    mock_tool_result.isError = False

    # Configure the mock MCP client
    mock_mcp_client.call_tool.return_value = mock_tool_result

    # Create mock tool schema
    mock_tool_schema = MagicMock()
    mock_tool_schema.name = "mcp_test_tool"
    mock_tool_schema.description = "MCP Test Tool"
    mock_tool_schema.input_schema = {"type": "object", "properties": {"param": {"type": "string"}}}

    mock_mcp_client.get_tools.return_value = [mock_tool_schema]

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Register the MCP tools
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.register_mcp_tools())

    # Act - Call the registered tool
    tool = agent.tools[0]
    tool_input = {"param": "test"}
    result = loop.run_until_complete(tool(tool_input))

    # Assert
    mock_mcp_client.call_tool.assert_called_once_with("mcp_test_tool", **tool_input)
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "MCP tool result"
    assert "is_error" not in result


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_mcp_tool_wrapper_error(mock_create_bedrock_client):
    """Test that the MCP tool wrapper function handles errors correctly."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Create mock tool response with error
    mock_tool_result = MagicMock()
    mock_tool_result.content = [MagicMock()]
    mock_tool_result.content[0].text = "Error message"
    mock_tool_result.isError = True

    # Configure the mock MCP client
    mock_mcp_client.call_tool.return_value = mock_tool_result

    # Create mock tool schema
    mock_tool_schema = MagicMock()
    mock_tool_schema.name = "mcp_error_tool"
    mock_tool_schema.description = "MCP Error Tool"
    mock_tool_schema.input_schema = {"type": "object", "properties": {}}

    mock_mcp_client.get_tools.return_value = [mock_tool_schema]

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Register the MCP tools
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.register_mcp_tools())

    # Act - Call the registered tool
    tool = agent.tools[0]
    result = loop.run_until_complete(tool({}))

    # Assert
    mock_mcp_client.call_tool.assert_called_once()
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Error message"
    assert result["is_error"] is True


@patch("agent_builder_sdk.agent.create_bedrock_client")
def test_mcp_tool_wrapper_unknown_content_type(mock_create_bedrock_client):
    """Test that the MCP tool wrapper function handles unknown content types correctly."""
    # Arrange
    system_prompt = "You are a helpful assistant."
    bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    mock_mcp_client = AsyncMock()

    # Create mock tool response with unknown content type
    mock_tool_result = MagicMock()
    mock_tool_result.content = [MagicMock()]
    # This content object doesn't have a 'text' attribute
    del mock_tool_result.content[0].text
    # Make the content object return a string when converted to string
    mock_tool_result.content[0].__str__ = MagicMock(return_value="Unknown content type")

    # Configure the mock MCP client
    mock_mcp_client.call_tool.return_value = mock_tool_result

    # Create mock tool schema
    mock_tool_schema = MagicMock()
    mock_tool_schema.name = "mcp_unknown_tool"
    mock_tool_schema.description = "MCP Unknown Content Tool"
    mock_tool_schema.input_schema = {"type": "object", "properties": {}}

    mock_mcp_client.get_tools.return_value = [mock_tool_schema]

    # Create the agent
    agent = Agent(
        system_prompt=system_prompt, bedrock_model_id=bedrock_model_id, mcp_client=mock_mcp_client
    )

    # Register the MCP tools
    loop = asyncio.get_event_loop()
    loop.run_until_complete(agent.register_mcp_tools())

    # Act - Call the registered tool
    tool = agent.tools[0]
    with patch("agent_builder_sdk.agent.logger") as mock_logger:
        result = loop.run_until_complete(tool({}))

    # Assert
    mock_mcp_client.call_tool.assert_called_once()
    mock_logger.warning.assert_called_once()
    assert result["content"][0]["type"] == "text"
    # We're just checking that some text was returned, not the exact content
    assert isinstance(result["content"][0]["text"], str)
