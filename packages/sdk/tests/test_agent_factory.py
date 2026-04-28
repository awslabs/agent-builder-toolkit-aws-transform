"""
Unit tests for agent factory functions.
"""

import os
from unittest import mock

from agent_builder_sdk.agent_factory import (
    create_default_async_subagent,
    create_default_orchestrator,
    create_default_orchestrator_with_subagent,
    create_default_subagent,
)


class TestAgentFactory:
    """Test cases for agent factory functions."""

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_create_default_orchestrator_with_defaults(
        self,
        mock_get_prompt,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with default parameters."""
        # Setup mocks
        mock_get_prompt.return_value = "test prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Call function
        result = create_default_orchestrator()

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify memory components were created
        mock_file_repo.assert_called_once_with(storage_path="/tmp/orchestrator_agent/memories")
        mock_episodic_memory.assert_called_once()
        mock_memory_manager.assert_called_once()
        mock_memory_tool.assert_called_once()

        # Verify conversation components
        mock_conversation_repo.assert_called_once_with(storage_dir="/tmp/orchestrator_agent")

        # Verify hooks
        mock_conversation_hook.assert_called_once()
        mock_memory_hook.assert_called_once()

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["system_prompt"] == "test prompt"
        assert call_kwargs["mcp_clients"] is None
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    @mock.patch("agent_builder_sdk.agent_factory.get_base_guardrail_prompt")
    def test_create_default_orchestrator_with_defaults_and_guardrails(
        self,
        mock_get_base_guardrail_prompt,
        mock_get_prompt,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with default parameters."""
        # Setup mocks
        mock_get_base_guardrail_prompt.return_value = "test guardrail"
        mock_get_prompt.return_value = "test prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Call function
        result = create_default_orchestrator(with_base_guardrails=True)

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify memory components were created
        mock_file_repo.assert_called_once_with(storage_path="/tmp/orchestrator_agent/memories")
        mock_episodic_memory.assert_called_once()
        mock_memory_manager.assert_called_once()
        mock_memory_tool.assert_called_once()

        # Verify conversation components
        mock_conversation_repo.assert_called_once_with(storage_dir="/tmp/orchestrator_agent")

        # Verify hooks
        mock_conversation_hook.assert_called_once()
        mock_memory_hook.assert_called_once()

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["system_prompt"] == "test prompt" + "\n" + "test guardrail"
        assert call_kwargs["mcp_clients"] is None
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    def test_create_default_orchestrator_with_custom_params(
        self,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with custom parameters."""
        # Setup
        mock_mcp_client = mock.Mock()
        custom_storage_dir = "/custom/storage"
        custom_prompt = "Custom system prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Call function
        result = create_default_orchestrator(
            mcp_client=mock_mcp_client, storage_dir=custom_storage_dir, system_prompt=custom_prompt
        )

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify custom storage path used
        mock_file_repo.assert_called_once_with(storage_path=f"{custom_storage_dir}/memories")
        mock_conversation_repo.assert_called_once_with(storage_dir=custom_storage_dir)

        # Verify orchestrator creation with custom params
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["system_prompt"] == custom_prompt
        assert call_kwargs["mcp_clients"] == [mock_mcp_client]

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_create_default_orchestrator_none_mcp_client(
        self,
        mock_get_prompt,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with None MCP client."""
        # Setup
        mock_get_prompt.return_value = "test prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Call function with explicit None
        result = create_default_orchestrator(mcp_client=None)

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify orchestrator creation with None MCP client
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["mcp_clients"] is None

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"})
    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_create_default_orchestrator_with_aws_region_env(
        self,
        mock_get_prompt,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator uses AWS_REGION environment variable."""
        # Setup
        mock_get_prompt.return_value = "test prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Call function
        result = create_default_orchestrator()

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify orchestrator uses environment AWS region
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["region_name"] == "us-west-2"

    @mock.patch("agent_builder_sdk.agent_factory.BaseSubagent")
    def test_create_default_subagent_with_defaults(self, mock_subagent):
        """Test creating subagent with default parameters."""
        # Setup
        mock_subagent_instance = mock.Mock()
        mock_subagent.return_value = mock_subagent_instance

        # Call function
        result = create_default_subagent(system_prompt="prompt")

        # Verify result
        assert result == mock_subagent_instance

        # Verify subagent creation
        mock_subagent.assert_called_once()
        call_kwargs = mock_subagent.call_args.kwargs
        assert call_kwargs["system_prompt"] == "prompt"
        assert call_kwargs["mcp_clients"] is None
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"

    @mock.patch("agent_builder_sdk.agent_factory.BaseSubagent")
    def test_create_default_subagent_with_custom_params(self, mock_subagent):
        """Test creating subagent with custom parameters."""
        # Setup
        mock_mcp_client = mock.Mock()
        custom_prompt = "Custom system prompt"
        mock_subagent_instance = mock.Mock()
        mock_subagent.return_value = mock_subagent_instance

        # Call function
        result = create_default_subagent(mcp_client=mock_mcp_client, system_prompt=custom_prompt)

        # Verify result
        assert result == mock_subagent_instance

        # Verify subagent creation with custom params
        mock_subagent.assert_called_once()
        call_kwargs = mock_subagent.call_args.kwargs
        assert call_kwargs["system_prompt"] == custom_prompt
        assert call_kwargs["mcp_clients"] == [mock_mcp_client]

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"})
    @mock.patch("agent_builder_sdk.agent_factory.BaseSubagent")
    def test_create_default_subagent_with_aws_region_env(self, mock_subagent):
        """Test creating subagent uses AWS_REGION environment variable."""
        # Setup
        mock_subagent_instance = mock.Mock()
        mock_subagent.return_value = mock_subagent_instance

        # Call function
        result = create_default_subagent(system_prompt="prompt")

        # Verify result
        assert result == mock_subagent_instance

        # Verify subagent uses environment AWS region
        mock_subagent.assert_called_once()
        call_kwargs = mock_subagent.call_args.kwargs
        assert call_kwargs["region_name"] == "us-west-2"

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_create_default_orchestrator_with_subagent(
        self,
        mock_send_message_tools,
        mock_subagent_registry_tools,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with subagent tools."""
        # Setup mocks
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        mock_memory_tool_instance = mock.Mock()
        mock_memory_tool_instance.memory = mock.Mock(name="memory_tool")
        mock_memory_tool.return_value = mock_memory_tool_instance

        mock_subagent_registry = mock.Mock()
        mock_subagent_registry.discover_subagents = mock.Mock(name="discover_subagents")
        mock_subagent_registry_tools.return_value = mock_subagent_registry

        mock_send_message = mock.Mock()
        mock_send_message.send_message_to_subagent = mock.Mock(name="send_message_to_subagent")
        mock_send_message_tools.return_value = mock_send_message

        # Create test MCP client
        mock_mcp_client = mock.Mock()

        # Call function
        result = create_default_orchestrator_with_subagent(
            system_prompt="test prompt", mcp_client=mock_mcp_client, storage_dir="/custom/path"
        )

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify memory components setup
        mock_file_repo.assert_called_once_with(storage_path="/custom/path/memories")
        mock_episodic_memory.assert_called_once()
        mock_memory_manager.assert_called_once()
        mock_memory_tool.assert_called_once()

        # Verify conversation components
        mock_conversation_repo.assert_called_once_with(storage_dir="/custom/path")
        mock_conversation_hook.assert_called_once()
        mock_memory_hook.assert_called_once()

        # Verify subagent tools setup
        mock_subagent_registry_tools.assert_called_once()
        mock_send_message_tools.assert_called_once()

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["system_prompt"] == "test prompt"
        assert call_kwargs["mcp_clients"] == [mock_mcp_client]
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"

        # Verify custom tools
        custom_tools = call_kwargs["custom_tools"]
        assert len(custom_tools) == 3
        assert mock_memory_tool_instance.memory in custom_tools
        assert mock_subagent_registry.discover_subagents in custom_tools
        assert mock_send_message.send_message_to_subagent in custom_tools

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    @mock.patch("agent_builder_sdk.agent_factory.get_base_guardrail_prompt")
    def test_create_default_orchestrator_with_subagent_and_guardrails(
        self,
        mock_get_base_guardrail_prompt,
        mock_send_message_tools,
        mock_subagent_registry_tools,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with subagent tools."""
        # Setup mocks
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        mock_memory_tool_instance = mock.Mock()
        mock_memory_tool_instance.memory = mock.Mock(name="memory_tool")
        mock_memory_tool.return_value = mock_memory_tool_instance

        mock_subagent_registry = mock.Mock()
        mock_subagent_registry.discover_subagents = mock.Mock(name="discover_subagents")
        mock_subagent_registry_tools.return_value = mock_subagent_registry

        mock_send_message = mock.Mock()
        mock_send_message.send_message_to_subagent = mock.Mock(name="send_message_to_subagent")
        mock_send_message_tools.return_value = mock_send_message

        mock_get_base_guardrail_prompt.return_value = "test_guardrail"

        # Create test MCP client
        mock_mcp_client = mock.Mock()

        # Call function
        result = create_default_orchestrator_with_subagent(
            system_prompt="test prompt",
            mcp_client=mock_mcp_client,
            storage_dir="/custom/path",
            with_base_guardrails=True,
        )

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify memory components setup
        mock_file_repo.assert_called_once_with(storage_path="/custom/path/memories")
        mock_episodic_memory.assert_called_once()
        mock_memory_manager.assert_called_once()
        mock_memory_tool.assert_called_once()

        # Verify conversation components
        mock_conversation_repo.assert_called_once_with(storage_dir="/custom/path")
        mock_conversation_hook.assert_called_once()
        mock_memory_hook.assert_called_once()

        # Verify subagent tools setup
        mock_subagent_registry_tools.assert_called_once()
        mock_send_message_tools.assert_called_once()

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs
        assert call_kwargs["system_prompt"] == "test prompt\ntest_guardrail"
        assert call_kwargs["mcp_clients"] == [mock_mcp_client]
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"

        # Verify custom tools
        custom_tools = call_kwargs["custom_tools"]
        assert len(custom_tools) == 3
        assert mock_memory_tool_instance.memory in custom_tools
        assert mock_subagent_registry.discover_subagents in custom_tools
        assert mock_send_message.send_message_to_subagent in custom_tools

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_create_default_orchestrator_with_custom_tools(
        self,
        mock_get_prompt,
        mock_memory_hook,
        mock_conversation_hook,
        mock_conversation_repo,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with additional custom tools."""
        # Setup mocks
        mock_get_prompt.return_value = "test prompt"
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        mock_memory_tool_instance = mock.Mock()
        mock_memory_tool_instance.memory = mock.Mock(name="memory_tool")
        mock_memory_tool.return_value = mock_memory_tool_instance

        # Create custom tools
        custom_tool_1 = mock.Mock(name="custom_tool_1")
        custom_tool_2 = mock.Mock(name="custom_tool_2")

        # Call function with custom tools
        result = create_default_orchestrator(custom_tools=[custom_tool_1, custom_tool_2])

        # Verify result
        assert result == mock_orchestrator_instance

        # Verify orchestrator creation
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args.kwargs

        # Verify custom tools are included
        custom_tools = call_kwargs["custom_tools"]
        assert mock_memory_tool_instance.memory in custom_tools
        assert custom_tool_1 in custom_tools
        assert custom_tool_2 in custom_tools

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    def test_create_default_orchestrator_with_model_parameter(
        self,
        mock_memory_hook,
        mock_conversation_hook,
        mock_memory_tool,
        mock_memory_manager,
        mock_episodic_memory,
        mock_file_repo,
        mock_conversation_repo,
        mock_orchestrator,
    ):
        """Test creating orchestrator with custom model parameter."""
        mock_model = mock.Mock()
        mock_orchestrator_instance = mock.Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        result = create_default_orchestrator(model=mock_model)

        assert result == mock_orchestrator_instance
        mock_orchestrator.assert_called_once()
        call_kwargs = mock_orchestrator.call_args[1]
        assert call_kwargs["model"] == mock_model

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("agent_builder_sdk.agent_factory.BaseSubagent")
    def test_create_default_subagent_with_model_parameter(self, mock_subagent):
        """Test creating subagent with custom model parameter."""
        mock_model = mock.Mock()
        mock_subagent_instance = mock.Mock()
        mock_subagent.return_value = mock_subagent_instance
        mock_custom_tool_instance = mock.Mock()

        result = create_default_subagent(
            system_prompt="prompt", model=mock_model, custom_tools=[mock_custom_tool_instance]
        )

        assert result == mock_subagent_instance
        mock_subagent.assert_called_once_with(
            system_prompt="prompt",
            mcp_clients=None,
            region_name="us-east-1",
            model=mock_model,
            custom_tools=[mock_custom_tool_instance],
            metrics_config=None,
        )

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseSubagent")
    def test_create_default_async_subagent_with_defaults(self, mock_async_subagent):
        """Test creating async subagent with default parameters."""
        # Setup
        mock_async_subagent_instance = mock.Mock()
        mock_async_subagent.return_value = mock_async_subagent_instance

        # Call function
        result = create_default_async_subagent(system_prompt="prompt")

        # Verify result
        assert result == mock_async_subagent_instance

        # Verify async subagent creation
        mock_async_subagent.assert_called_once()
        call_kwargs = mock_async_subagent.call_args.kwargs
        assert call_kwargs["system_prompt"] == "prompt"
        assert call_kwargs["mcp_clients"] is None
        assert call_kwargs["region_name"] == os.getenv("AWS_REGION") or "us-east-1"
        assert call_kwargs["model"] is None
        assert call_kwargs["custom_tools"] is None

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseSubagent")
    def test_create_default_async_subagent_with_custom_params(self, mock_async_subagent):
        """Test creating async subagent with custom parameters."""
        # Setup
        mock_mcp_client = mock.Mock()
        mock_model = mock.Mock()
        mock_custom_tool = mock.Mock()
        custom_prompt = "Custom system prompt"
        mock_async_subagent_instance = mock.Mock()
        mock_async_subagent.return_value = mock_async_subagent_instance

        # Call function
        result = create_default_async_subagent(
            system_prompt=custom_prompt,
            mcp_client=mock_mcp_client,
            model=mock_model,
            custom_tools=[mock_custom_tool],
        )

        # Verify result
        assert result == mock_async_subagent_instance

        # Verify async subagent creation with custom params
        mock_async_subagent.assert_called_once()
        call_kwargs = mock_async_subagent.call_args.kwargs
        assert call_kwargs["system_prompt"] == custom_prompt
        assert call_kwargs["mcp_clients"] == [mock_mcp_client]
        assert call_kwargs["model"] == mock_model
        assert call_kwargs["custom_tools"] == [mock_custom_tool]

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"})
    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseSubagent")
    def test_create_default_async_subagent_with_aws_region_env(self, mock_async_subagent):
        """Test creating async subagent uses AWS_REGION environment variable."""
        # Setup
        mock_async_subagent_instance = mock.Mock()
        mock_async_subagent.return_value = mock_async_subagent_instance

        # Call function
        result = create_default_async_subagent(system_prompt="prompt")

        # Verify result
        assert result == mock_async_subagent_instance

        # Verify async subagent uses environment AWS region
        mock_async_subagent.assert_called_once()
        call_kwargs = mock_async_subagent.call_args.kwargs
        assert call_kwargs["region_name"] == "us-west-2"
