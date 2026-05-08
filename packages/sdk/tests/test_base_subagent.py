# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the BaseSubagent class."""

from unittest import mock
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest
from strands.agent import AgentResult
from strands.telemetry import EventLoopMetrics
from strands.tools.mcp import MCPAgentTool, MCPClient
from strands.types import PaginatedList
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent, BaseSubagent
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    ProcessMessageRequest,
)


@pytest.fixture(autouse=True)
def patch_create_with_shared_capacity_role(mock_model):
    target = "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
    with patch(target, spec_set=True, autospec=True, return_value=mock_model) as patched:
        yield patched


@pytest.fixture
def subagent(mock_model):
    return BaseSubagent(system_prompt="Test prompt")


@pytest.fixture
def async_subagent(mock_model):
    return AsyncBaseSubagent(system_prompt="Test prompt")


def test_initialization_defaults(subagent):
    """Test subagent initialization with default parameters."""
    assert subagent.system_prompt == "Test prompt"
    assert subagent.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert subagent.region_name == "us-east-1"
    assert subagent.custom_tools == []
    assert hasattr(subagent, "model")


def test_initialization_with_custom_parameters(mock_model):
    """Test subagent initialization with custom parameters."""
    mock_tools = [Mock(), Mock()]

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(
            system_prompt="Custom prompt",
            custom_tools=mock_tools,
            region_name="us-west-2",
            model_id="custom-model-id",
        )

    assert subagent.system_prompt == "Custom prompt"
    assert subagent.model_id == "custom-model-id"
    assert subagent.region_name == "us-west-2"
    assert subagent.custom_tools == mock_tools


def test_process_message(subagent, agent_result):
    request = ProcessMessageRequest(message="Test message", context=ConversationContext())

    with patch.object(
        subagent, "invoke_async", autospec=True, return_value=agent_result
    ) as invoke_async:
        result = subagent.process_message(request)

        invoke_async.assert_called_once_with("Test message")
        assert result == agent_result


async def test_process_message_async(async_subagent, agent_result):
    request = ProcessMessageRequest(message="Test message", context=ConversationContext())

    with patch.object(
        async_subagent, "invoke_async", autospec=True, return_value=agent_result
    ) as invoke_async:
        result = await async_subagent.process_message_async(request)

        invoke_async.assert_called_once_with("Test message")
        assert result == agent_result


def test_subagent_with_empty_tools_list(mock_model):
    """Test subagent initialization with empty tools list."""
    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(system_prompt="Test prompt", custom_tools=[])

    assert subagent.system_prompt == "Test prompt"
    assert subagent.custom_tools == []


def test_subagent_with_tools(mock_model):
    """Test subagent initialization with tools."""
    mock_tools = [Mock(), Mock()]

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(system_prompt="Test prompt", custom_tools=mock_tools)

    assert subagent.custom_tools == mock_tools


def test_subagent_bedrock_model_creation(mock_model):
    """Test that BedrockModel is created with correct parameters."""
    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ) as mock_factory:
        subagent = BaseSubagent(
            system_prompt="Test prompt",
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id="test-guardrail",
            guardrail_version="2",
        )

        # Verify BedrockModelFactory was called with correct parameters
        mock_factory.assert_called_once_with(
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id="test-guardrail",
            guardrail_version="2",
        )
        assert subagent.model == mock_model


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_initialize_bedrock_model_default_credentials(mock_factory, mock_model):
    """Test BedrockModel initialization with default credentials."""
    mock_factory.return_value = mock_model

    subagent = BaseSubagent(system_prompt="Test prompt")

    # Verify BedrockModelFactory was called with default parameters
    mock_factory.assert_called_once_with(
        model_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name="us-east-1",
        guardrail_id=None,
        guardrail_version=None,
    )
    assert subagent.model == mock_model


async def test_process_message_async_enters_mcp_client_context(mock_model, agent_result):
    mock_tool_1 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_tool_2 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_mcp_client_1 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_2 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_1.list_tools_sync.return_value = PaginatedList([mock_tool_1])
    mock_mcp_client_2.list_tools_sync.return_value = PaginatedList([mock_tool_2])

    subagent = AsyncBaseSubagent(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client_1, mock_mcp_client_2],
    )

    # Called when combining tools during initialisation
    mock_mcp_client_1.__enter__.reset_mock()
    mock_mcp_client_2.__enter__.reset_mock()
    mock_mcp_client_1.__exit__.reset_mock()
    mock_mcp_client_2.__exit__.reset_mock()

    with patch.object(subagent, "invoke_async", autospec=True, return_value=agent_result):
        request = ProcessMessageRequest(message="message", context=ConversationContext())
        await subagent.process_message_async(request)

    assert subagent.mcp_clients == [mock_mcp_client_1, mock_mcp_client_2]
    mock_mcp_client_1.__enter__.assert_called_once()
    mock_mcp_client_2.__enter__.assert_called_once()
    mock_mcp_client_1.__exit__.assert_called_once()
    mock_mcp_client_2.__exit__.assert_called_once()


def test_combine_tools_with_mcp_and_custom(mock_model):
    """Test combining MCP tools with custom tools."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(tool_name="mcp_tool1"), Mock(tool_name="mcp_tool2")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)
    custom_tools = [Mock(tool_name="custom_tool1")]

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(
            system_prompt="Test prompt", mcp_clients=[mock_mcp_client], custom_tools=custom_tools
        )

        combined_tools = subagent._combine_tools()
        assert len(combined_tools) == 3
        assert mock_mcp_tools[0] in combined_tools
        assert mock_mcp_tools[1] in combined_tools
        assert custom_tools[0] in combined_tools


def test_combine_tools_with_multiple_mcp_and_custom(mock_model):
    """Test combining multiple MCP server tools with custom tools."""
    mock_mcp_client1 = Mock()
    mock_mcp_client1.__enter__ = Mock(return_value=mock_mcp_client1)
    mock_mcp_client1.__exit__ = Mock(return_value=None)
    mock_mcp_tools1 = [Mock(tool_name="mcp_tool1"), Mock(tool_name="mcp_tool2")]
    mock_mcp_client1.list_tools_sync = Mock(return_value=mock_mcp_tools1)

    mock_mcp_client2 = Mock()
    mock_mcp_client2.__enter__ = Mock(return_value=mock_mcp_client2)
    mock_mcp_client2.__exit__ = Mock(return_value=None)
    mock_mcp_tools2 = [Mock(tool_name="mcp_tool3"), Mock(tool_name="mcp_tool4")]
    mock_mcp_client2.list_tools_sync = Mock(return_value=mock_mcp_tools2)

    custom_tools = [Mock(tool_name="custom_tool1")]

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(
            system_prompt="Test prompt",
            mcp_clients=[mock_mcp_client1, mock_mcp_client2],
            custom_tools=custom_tools,
        )

        combined_tools = subagent._combine_tools()
        assert len(combined_tools) == 5
        assert mock_mcp_tools1[0] in combined_tools
        assert mock_mcp_tools1[1] in combined_tools
        assert custom_tools[0] in combined_tools
        assert mock_mcp_tools2[0] in combined_tools
        assert mock_mcp_tools2[1] in combined_tools


def test_combine_tools_duplicate_names_raises_error(mock_model):
    """Test that duplicate tool names raise ValueError."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(tool_name="duplicate_tool")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)
    custom_tools = [Mock(tool_name="duplicate_tool")]

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        with pytest.raises(ValueError, match="Duplicate tool name found: 'duplicate_tool'"):
            BaseSubagent(
                system_prompt="Test prompt",
                mcp_clients=[mock_mcp_client],
                custom_tools=custom_tools,
            )


def test_process_message_with_mcp_clients(mock_model):
    """Test process_message with MCP clients."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_client.list_tools_sync = Mock(return_value=[])

    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(system_prompt="Test prompt", mcp_clients=[mock_mcp_client])

    # Mock the invoke_async method
    mock_result = Mock()
    with patch.object(subagent, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_result

        request = ProcessMessageRequest(message="Test message", context=ConversationContext())
        result = subagent.process_message(request)

        # Verify the result
        assert result == mock_result
        mock_invoke_async.assert_called_once_with("Test message")


def test_process_message_without_mcp_clients(mock_model):
    """Test process_message without MCP clients."""
    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(system_prompt="Test prompt")

    # Mock the invoke_async method
    mock_result = Mock()
    with patch.object(subagent, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_result

        request = ProcessMessageRequest(message="Test message", context=ConversationContext())
        result = subagent.process_message(request)

        # Verify the result
        assert result == mock_result
        mock_invoke_async.assert_called_once_with("Test message")


def test_process_message_handles_exceptions(mock_model):
    """Test process_message handles exceptions gracefully."""
    with patch(
        "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        subagent = BaseSubagent(system_prompt="Test prompt")

    # Mock the invoke_async method to raise an exception
    with patch.object(subagent, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.side_effect = Exception("Test error")

        request = ProcessMessageRequest(message="Test message", context=ConversationContext())
        with pytest.raises(Exception, match="Test error"):
            subagent.process_message(request)


class TestBaseSubagentIntegration:
    """Integration tests for BaseSubagent."""

    def test_full_message_processing_flow(self, mock_model):
        """Test the complete message processing flow."""
        with patch(
            "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role",
            return_value=mock_model,
        ):
            subagent = BaseSubagent(system_prompt="Test prompt")

        # Create a proper mock response
        response_content = [ContentBlock(text="Test response")]
        response = Message(role="assistant", content=response_content)
        mock_result = AgentResult(
            message=response, stop_reason="end_turn", metrics=EventLoopMetrics(), state={}
        )

        # Mock the invoke_async method to avoid streaming issues
        with patch.object(subagent, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
            mock_invoke_async.return_value = mock_result

            # Process the message
            request = ProcessMessageRequest(message="Hello", context=ConversationContext())
            result = subagent.process_message(request)

            # Verify the flow
            mock_invoke_async.assert_called_once_with("Hello")
            assert result == mock_result
            assert result.message == response


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_subagent_tool_filtering(mock_factory, mock_model):
    """Test that excluded tools are filtered out."""
    mock_factory.return_value = mock_model

    # Create mock tools
    allowed_tool = Mock()
    allowed_tool.tool_name = "allowed_tool"

    excluded_tool = Mock()
    excluded_tool.tool_name = "put_job_plan"  # This should be filtered out

    custom_tools = [allowed_tool, excluded_tool]

    subagent = BaseSubagent(system_prompt="Test prompt", custom_tools=custom_tools)

    # Get combined tools
    combined_tools = subagent._combine_tools()

    # Verify only allowed tool is included
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "allowed_tool" in tool_names
    assert "put_job_plan" not in tool_names


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_subagent_default_tool_filtering(mock_factory, mock_model):
    """Test that default excluded tools are filtered out when no excluded_tool_names provided."""
    mock_factory.return_value = mock_model

    # Create mock tools including ones that should be excluded by default
    allowed_tool = Mock()
    allowed_tool.tool_name = "allowed_tool"

    put_job_plan_tool = Mock()
    put_job_plan_tool.tool_name = "put_job_plan"  # Should be excluded by default

    update_job_status_tool = Mock()
    update_job_status_tool.tool_name = "update_job_status"  # Should be excluded by default

    custom_tools = [allowed_tool, put_job_plan_tool, update_job_status_tool]

    # Create subagent without specifying excluded_tool_names (should use defaults)
    subagent = BaseSubagent(system_prompt="Test prompt", custom_tools=custom_tools)

    # Get combined tools
    combined_tools = subagent._combine_tools()

    # Verify only allowed tool is included, default excluded tools are filtered out
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "allowed_tool" in tool_names
    assert "put_job_plan" not in tool_names
    assert "update_job_status" not in tool_names


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_subagent_custom_excluded_tools(mock_factory, mock_model):
    """Test that custom excluded tool list works."""
    mock_factory.return_value = mock_model

    # Create mock tools
    tool1 = Mock()
    tool1.tool_name = "tool1"

    tool2 = Mock()
    tool2.tool_name = "tool2"

    custom_tools = [tool1, tool2]

    subagent = BaseSubagent(
        system_prompt="Test prompt",
        custom_tools=custom_tools,
        excluded_tool_names=["tool2"],  # Custom exclusion list
    )

    # Get combined tools
    combined_tools = subagent._combine_tools()

    # Verify only tool1 is included
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "tool1" in tool_names
    assert "tool2" not in tool_names


@mock.patch("agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory")
def test_subagent_with_model_parameter(mock_bedrock_factory):
    """Test BaseSubagent with custom model parameter."""
    mock_model = mock.Mock()

    subagent = BaseSubagent(system_prompt="Test prompt", model=mock_model)

    # Verify Bedrock factory was not called when model provided
    mock_bedrock_factory.create_with_shared_capacity_role.assert_not_called()

    # Verify model is accessible through parent class
    assert hasattr(subagent, "model")


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_subagent_excluded_mcp_tool_names(mock_factory, mock_model):
    """Test that excluded_mcp_tool_names filters MCP tools."""
    mock_factory.return_value = mock_model

    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [
        Mock(tool_name="mcp_included"),
        Mock(tool_name="mcp_excluded"),
    ]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)

    subagent = BaseSubagent(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = subagent._combine_tools()
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "mcp_included" in tool_names
    assert "mcp_excluded" not in tool_names


@patch(
    "agent_builder_sdk.base_subagent.base_subagent.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_subagent_excluded_mcp_and_custom_tools(mock_factory, mock_model):
    """Test that both excluded_tool_names and excluded_mcp_tool_names work together."""
    mock_factory.return_value = mock_model

    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(tool_name="mcp_excluded")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)

    custom_tools = [Mock(tool_name="custom_excluded")]

    subagent = BaseSubagent(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        custom_tools=custom_tools,
        excluded_tool_names={"custom_excluded"},
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = subagent._combine_tools()
    assert len(combined_tools) == 0
