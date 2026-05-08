# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the BaseOrchestrator class."""

from unittest import mock
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest
from strands.tools.mcp import MCPAgentTool, MCPClient
from strands.types import PaginatedList

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import (
    AsyncBaseOrchestrator,
    BaseOrchestrator,
)
from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    CURRENT_SOURCE_ID_KEY,
    CURRENT_SOURCE_TYPE_KEY,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import (
    ConversationHookProvider,
)
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)


@pytest.fixture(autouse=True)
def patch_create_with_shared_capacity_role(mock_model):
    target = "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    with patch(target, spec_set=True, autospec=True, return_value=mock_model) as patched:
        yield patched


@pytest.fixture
def orchestrator():
    return BaseOrchestrator(system_prompt="Test prompt")


@pytest.fixture
def async_orchestrator():
    return AsyncBaseOrchestrator(system_prompt="Test prompt")


def test_initialization_defaults(orchestrator):
    """Test orchestrator initialization with default parameters."""
    assert orchestrator.system_prompt == "Test prompt"
    assert orchestrator.model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert orchestrator.region_name == "us-east-1"
    assert orchestrator.custom_tools == []
    assert hasattr(orchestrator, "model")


def test_initialization_with_custom_parameters(mock_model):
    """Test orchestrator initialization with custom parameters."""
    mock_tools = [Mock(), Mock()]
    mock_hooks = [create_autospec(ConversationHookProvider), create_autospec(MemoryHookProvider)]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Custom prompt",
            custom_tools=mock_tools,
            hooks=mock_hooks,
            region_name="us-west-2",
            model_id="custom-model-id",
        )

    assert orchestrator.system_prompt == "Custom prompt"
    assert orchestrator.model_id == "custom-model-id"
    assert orchestrator.region_name == "us-west-2"
    assert orchestrator.custom_tools == mock_tools


def test_initialization_with_hooks(mock_model, mock_repository, mock_memory_manager):
    """Test orchestrator initialization with explicit hooks."""
    conversation_hook = ConversationHookProvider(repository=mock_repository)
    memory_hook = MemoryHookProvider(memory_manager=mock_memory_manager)
    hooks = [conversation_hook, memory_hook]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=hooks)

    # We can't easily check the hooks after initialization since they become a HookRegistry
    # But we can verify the orchestrator was created successfully
    assert orchestrator.system_prompt == "Test prompt"


def process_message_cases():
    return [
        (
            ConversationContext(agent_instance_id="test-agent"),
            "test-agent",
            MessageSourceType.SUBAGENT,
        ),
        (ConversationContext(user_id="test-user"), "test-user", MessageSourceType.USER),
        (ConversationContext(), "SYSTEM", MessageSourceType.NOTIFICATION),
    ]


@pytest.mark.parametrize(["context", "source_id", "source_type"], process_message_cases())
def test_process_message(orchestrator, agent_result, context, source_id, source_type):
    message = "Test message"
    request = ProcessMessageRequest(message=message, context=context)

    with patch.object(
        orchestrator, "invoke_with_source", autospec=True, return_value=agent_result
    ) as invoke_with_source:
        result = orchestrator.process_message(request)

        invoke_with_source.assert_called_once_with(message, source_id, source_type)
        assert result == agent_result


@pytest.mark.parametrize(["context", "source_id", "source_type"], process_message_cases())
async def test_process_message_async(
    async_orchestrator, agent_result, context, source_id, source_type
):
    message = "Test message"
    request = ProcessMessageRequest(message=message, context=context)

    with patch.object(
        async_orchestrator, "invoke_with_source_async", autospec=True, return_value=agent_result
    ) as invoke_with_source_async:
        result = await async_orchestrator.process_message_async(request)

        invoke_with_source_async.assert_awaited_once_with(message, source_id, source_type)
        assert result == agent_result


def test_invoke_with_source_sets_context(orchestrator):
    """Test that invoke_with_source sets the source context correctly."""
    # Mock the agent's state
    orchestrator.state = Mock()

    # Create a proper mock response
    mock_response = Mock()
    mock_response.message = "Test response"

    # Mock the entire invoke_async method to avoid the streaming issue
    with patch.object(orchestrator, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_response

        # Call invoke_with_source
        result = orchestrator.invoke_with_source(
            "test message", "test-source", MessageSourceType.USER
        )

        # Verify that the source context was set
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "test-source")

        # Verify that invoke_async was called with the message
        mock_invoke_async.assert_called_once_with("test message", invocation_state={})

        # Verify the result
        assert result == mock_response


def test_invoke_with_source_different_source_types(orchestrator):
    """Test invoke_with_source with different source types."""
    orchestrator.state = Mock()

    # Create a proper mock response
    mock_response = Mock()
    mock_response.message = "Test response"

    # Mock the entire invoke_async method to avoid the streaming issue
    with patch.object(orchestrator, "invoke_async", new_callable=AsyncMock) as mock_invoke_async:
        mock_invoke_async.return_value = mock_response

        # Test with SUBAGENT
        orchestrator.invoke_with_source("message1", "agent-123", MessageSourceType.SUBAGENT)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.SUBAGENT)
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "agent-123")

        # Reset mock
        orchestrator.state.reset_mock()

        # Test with NOTIFICATION
        orchestrator.invoke_with_source("message2", "SYSTEM", MessageSourceType.NOTIFICATION)
        orchestrator.state.set.assert_any_call(
            CURRENT_SOURCE_TYPE_KEY, MessageSourceType.NOTIFICATION
        )
        orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "SYSTEM")


async def test_invoke_with_source_async_enters_mcp_client_context(mock_model):
    mock_tool_1 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_tool_2 = create_autospec(MCPAgentTool, spec_set=True, instance=True)
    mock_mcp_client_1 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_2 = create_autospec(MCPClient, spec_set=True, instance=True)
    mock_mcp_client_1.list_tools_sync.return_value = PaginatedList([mock_tool_1])
    mock_mcp_client_2.list_tools_sync.return_value = PaginatedList([mock_tool_2])

    orchestrator = AsyncBaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client_1, mock_mcp_client_2],
    )

    # Called when combining tools during initialisation
    mock_mcp_client_1.__enter__.reset_mock()
    mock_mcp_client_2.__enter__.reset_mock()
    mock_mcp_client_1.__exit__.reset_mock()
    mock_mcp_client_2.__exit__.reset_mock()

    await orchestrator.invoke_with_source_async("message", "source-id", MessageSourceType.USER)

    assert orchestrator.mcp_clients == [mock_mcp_client_1, mock_mcp_client_2]
    mock_mcp_client_1.__enter__.assert_called_once()
    mock_mcp_client_2.__enter__.assert_called_once()
    mock_mcp_client_1.__exit__.assert_called_once()
    mock_mcp_client_2.__exit__.assert_called_once()


def test_set_current_source_context(orchestrator):
    """Test _set_current_source_context method."""
    orchestrator.state = Mock()
    orchestrator.agent_id = "test-agent-id"

    # Call the method
    orchestrator._set_current_source_context(MessageSourceType.USER, "user-123")

    # Verify state was set correctly
    orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
    orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "user-123")


def test_orchestrator_with_empty_hooks_list(mock_model):
    """Test orchestrator initialization with empty hooks list."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=[])

    assert orchestrator.system_prompt == "Test prompt"


def test_orchestrator_with_none_hooks(mock_model):
    """Test orchestrator initialization with None hooks."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", hooks=None)

    assert orchestrator.system_prompt == "Test prompt"


def test_orchestrator_with_tools(mock_model):
    """Test orchestrator initialization with tools."""
    mock_tools = [Mock(), Mock()]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", custom_tools=mock_tools)

    assert orchestrator.custom_tools == mock_tools


def test_orchestrator_bedrock_model_creation(mock_model):
    """Test that BedrockModel is created with correct parameters."""
    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ) as mock_factory:
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            model_id="custom-model",
            region_name="us-west-2",
        )

        # Verify factory was called with correct parameters
        mock_factory.assert_called_once_with(
            model_id="custom-model",
            region_name="us-west-2",
            guardrail_id=None,
            guardrail_version=None,
        )
        assert orchestrator.model == mock_model


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_initialize_bedrock_model_default_credentials(mock_factory, mock_model):
    """Test BedrockModel initialization with default credentials."""
    mock_factory.return_value = mock_model

    orchestrator = BaseOrchestrator(system_prompt="Test prompt")

    # Verify factory was called with default parameters
    mock_factory.assert_called_once_with(
        model_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name="us-east-1",
        guardrail_id=None,
        guardrail_version=None,
    )
    assert orchestrator.model == mock_model


class TestBaseOrchestratorIntegration:
    """Integration tests for BaseOrchestrator."""

    def test_full_message_processing_flow(self, mock_model):
        """Test the complete message processing flow."""
        with patch(
            "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
            return_value=mock_model,
        ):
            orchestrator = BaseOrchestrator(system_prompt="Test prompt")

        # Mock the necessary methods
        orchestrator.state = Mock()

        # Create a proper mock response
        mock_response = Mock()
        mock_response.message = "Test response"

        a2a_context = A2AContext(context_id="c-123", task_id=None)

        # Mock the entire invoke_async method to avoid the streaming issue
        with patch.object(
            orchestrator, "invoke_async", new_callable=AsyncMock
        ) as mock_invoke_async:
            mock_invoke_async.return_value = mock_response

            # Create a request
            request = ProcessMessageRequest(
                message="Hello",
                context=ConversationContext(user_id="test-user", a2a_context=a2a_context),
            )

            # Process the message
            result = orchestrator.process_message(request)

            # Verify the flow
            orchestrator.state.set.assert_any_call(CURRENT_SOURCE_TYPE_KEY, MessageSourceType.USER)
            orchestrator.state.set.assert_any_call(CURRENT_SOURCE_ID_KEY, "test-user")

            # Verify invoke_async was called
            mock_invoke_async.assert_called_once_with(
                "Hello", invocation_state={"a2a_context": a2a_context}
            )

            # Verify the result
            assert result == mock_response


def test_initialization_with_mcp_clients(mock_model, mock_repository):
    """Test orchestrator initialization with MCP clients."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_client.list_tools_sync = Mock(return_value=[Mock(), Mock()])

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            mcp_clients=[mock_mcp_client],
        )

        assert orchestrator.mcp_clients == [mock_mcp_client]
        mock_mcp_client.list_tools_sync.assert_called_once()


def test_combine_tools_with_mcp_and_custom():
    """Test combining MCP tools with custom tools."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(name="mcp_tool1"), Mock(name="mcp_tool2")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)
    custom_tools = [Mock(name="custom_tool1")]

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt", mcp_clients=[mock_mcp_client], custom_tools=custom_tools
        )

        combined_tools = orchestrator._combine_tools()
        assert len(combined_tools) == 3
        assert mock_mcp_tools[0] in combined_tools
        assert mock_mcp_tools[1] in combined_tools
        assert custom_tools[0] in combined_tools


def test_combine_tools_with_multiple_mcp_and_custom():
    """Test combining multiple MCP server tools with custom tools."""
    mock_mcp_client1 = Mock()
    mock_mcp_client1.__enter__ = Mock(return_value=mock_mcp_client1)
    mock_mcp_client1.__exit__ = Mock(return_value=None)
    mock_mcp_tools1 = [Mock(name="mcp_tool1"), Mock(name="mcp_tool2")]
    mock_mcp_client1.list_tools_sync = Mock(return_value=mock_mcp_tools1)
    custom_tools = [Mock(name="custom_tool1")]
    mock_mcp_client2 = Mock()
    mock_mcp_client2.__enter__ = Mock(return_value=mock_mcp_client2)
    mock_mcp_client2.__exit__ = Mock(return_value=None)
    mock_mcp_tools2 = [Mock(name="mcp_tool3"), Mock(name="mcp_tool4")]
    mock_mcp_client2.list_tools_sync = Mock(return_value=mock_mcp_tools2)

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
    ):
        orchestrator = BaseOrchestrator(
            system_prompt="Test prompt",
            mcp_clients=[mock_mcp_client1, mock_mcp_client2],
            custom_tools=custom_tools,
        )

        combined_tools = orchestrator._combine_tools()
        assert len(combined_tools) == 5
        assert mock_mcp_tools1[0] in combined_tools
        assert mock_mcp_tools1[1] in combined_tools
        assert custom_tools[0] in combined_tools
        assert mock_mcp_tools2[0] in combined_tools
        assert mock_mcp_tools2[1] in combined_tools


def test_invoke_with_source_with_mcp_clients(mock_model):
    """Test invoke_with_source with MCP clients."""
    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_client.list_tools_sync = Mock(return_value=[])

    with patch(
        "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role",
        return_value=mock_model,
    ):
        orchestrator = BaseOrchestrator(system_prompt="Test prompt", mcp_clients=[mock_mcp_client])

        # Test that MCP clients are properly stored
        assert orchestrator.mcp_clients == [mock_mcp_client]

        # Test context setting
        orchestrator._set_current_source_context(MessageSourceType.USER, "user123")
        assert orchestrator.state.get("current_source_type") == MessageSourceType.USER
        assert orchestrator.state.get("current_source_id") == "user123"


@mock.patch("agent_builder_sdk.orchestrator_strands.base_orchestrator.BedrockModelFactory")
def test_orchestrator_with_model_parameter(mock_bedrock_factory):
    """Test BaseOrchestrator with custom model parameter."""
    mock_model = mock.Mock()

    orchestrator = BaseOrchestrator(system_prompt="Test prompt", model=mock_model)

    # Verify Bedrock factory was not called when model provided
    mock_bedrock_factory.create_with_shared_capacity_role.assert_not_called()

    # Verify model is accessible through parent class
    assert hasattr(orchestrator, "model")


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_orchestrator_excluded_mcp_tool_names(mock_factory, mock_model):
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

    orchestrator = BaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = orchestrator._combine_tools()
    tool_names = [tool.tool_name for tool in combined_tools]
    assert "mcp_included" in tool_names
    assert "mcp_excluded" not in tool_names


@patch(
    "agent_builder_sdk.bedrock_model_factory.BedrockModelFactory.create_with_shared_capacity_role"
)
def test_orchestrator_excluded_mcp_and_custom_tools(mock_factory, mock_model):
    """Test that both excluded_tool_names and excluded_mcp_tool_names work together."""
    mock_factory.return_value = mock_model

    mock_mcp_client = Mock()
    mock_mcp_client.__enter__ = Mock(return_value=mock_mcp_client)
    mock_mcp_client.__exit__ = Mock(return_value=None)
    mock_mcp_tools = [Mock(tool_name="mcp_excluded")]
    mock_mcp_client.list_tools_sync = Mock(return_value=mock_mcp_tools)

    custom_tools = [Mock(tool_name="custom_excluded")]

    orchestrator = BaseOrchestrator(
        system_prompt="Test prompt",
        mcp_clients=[mock_mcp_client],
        custom_tools=custom_tools,
        excluded_tool_names={"custom_excluded"},
        excluded_mcp_tool_names={"mcp_excluded"},
    )

    combined_tools = orchestrator._combine_tools()
    assert len(combined_tools) == 0
