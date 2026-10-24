# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for agent factory functions.
"""

import os
from unittest import mock

from agent_builder_sdk.agent_factory import (
    create_default_async_orchestrator,
    create_default_async_orchestrator_with_subagent,
    create_default_async_subagent,
    create_default_orchestrator,
    create_default_orchestrator_with_subagent,
    create_default_subagent,
)
from agent_builder_sdk.orchestrator_strands.hooks.blank_reply_hook_provider import (
    BlankReplyHookProvider,
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
    def test_boto_client_config_forwarded_to_orchestrator(
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
        """boto_client_config is forwarded to the orchestrator (default None, opt-in when set)."""
        from botocore.config import Config as BotocoreConfig

        mock_get_prompt.return_value = "p"
        mock_orchestrator.return_value = mock.Mock()

        create_default_orchestrator()
        assert mock_orchestrator.call_args.kwargs["boto_client_config"] is None

        mock_orchestrator.reset_mock()
        cfg = BotocoreConfig(read_timeout=300)
        create_default_orchestrator(boto_client_config=cfg)
        assert mock_orchestrator.call_args.kwargs["boto_client_config"] is cfg

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_injected_conversation_repository_is_used_not_rebuilt(
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
        """When a shared conversation_repository is injected (concurrent streaming),
        the factory uses it and does NOT build a new one."""
        mock_get_prompt.return_value = "test prompt"
        shared_repo = mock.Mock()

        create_default_orchestrator(conversation_repository=shared_repo)

        # factory did not build its own repo...
        mock_conversation_repo.assert_not_called()
        # ...and the hook got the injected instance
        assert mock_conversation_hook.call_args.kwargs["repository"] is shared_repo

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_no_injected_repository_builds_own(
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
        """Backward-compatible default: no injected repo → factory builds its own."""
        mock_get_prompt.return_value = "test prompt"

        create_default_orchestrator(storage_dir="/tmp/x")

        mock_conversation_repo.assert_called_once_with(storage_dir="/tmp/x")
        assert (
            mock_conversation_hook.call_args.kwargs["repository"]
            is mock_conversation_repo.return_value
        )

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_injected_memory_manager_is_used_not_rebuilt(
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
        """When a shared memory_manager is injected (concurrent streaming), the factory uses
        it and does NOT build its own — so the shared singleton agent and per-user streaming
        agents use the same (job-scoped) memory store instead of diverging per storage_dir."""
        mock_get_prompt.return_value = "test prompt"
        shared_mgr = mock.Mock()

        create_default_orchestrator(memory_manager=shared_mgr)

        # factory did NOT build its own memory chain...
        mock_file_repo.assert_not_called()
        mock_episodic_memory.assert_not_called()
        mock_memory_manager.assert_not_called()
        # ...and both memory surfaces got the injected instance
        assert mock_memory_tool.call_args.args[0] is shared_mgr
        assert mock_memory_hook.call_args.kwargs["memory_manager"] is shared_mgr

    @mock.patch("agent_builder_sdk.agent_factory.BaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.get_prompt_with_name")
    def test_no_injected_memory_manager_builds_own(
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
        """Backward-compatible default: no injected manager → factory builds its own memory
        chain under <storage_dir>/memories."""
        mock_get_prompt.return_value = "test prompt"

        create_default_orchestrator(storage_dir="/tmp/x")

        mock_file_repo.assert_called_once_with(storage_path=os.path.join("/tmp/x", "memories"))
        mock_memory_manager.assert_called_once()
        assert (
            mock_memory_hook.call_args.kwargs["memory_manager"] is mock_memory_manager.return_value
        )

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


class TestOrchestratorOptions:
    """Opt-in orchestrator options stay off by default."""

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_blank_reply_continuation_off_by_default(self, *mocks):
        mock_orchestrator = mocks[-1]
        mock_orchestrator.return_value = mock.Mock()

        create_default_async_orchestrator_with_subagent(system_prompt="task prompt")
        create_default_async_orchestrator(system_prompt="task prompt")

        for call in mock_orchestrator.call_args_list:
            hooks = call.kwargs["hooks"]
            assert not any(isinstance(h, BlankReplyHookProvider) for h in hooks)

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_blank_reply_continuation_adds_its_hook_when_enabled(self, *mocks):
        mock_orchestrator = mocks[-1]
        mock_orchestrator.return_value = mock.Mock()

        create_default_async_orchestrator_with_subagent(
            system_prompt="task prompt", enable_blank_reply_continuation=True
        )

        hooks = mock_orchestrator.call_args.kwargs["hooks"]
        assert hooks[0] is mocks[3].return_value
        assert isinstance(hooks[-1], BlankReplyHookProvider)

    @mock.patch("agent_builder_sdk.agent_factory.AsyncBaseOrchestrator")
    @mock.patch("agent_builder_sdk.agent_factory.FileSystemRepository")
    @mock.patch("agent_builder_sdk.agent_factory.EpisodicMemory")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryManager")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryTool")
    @mock.patch("agent_builder_sdk.agent_factory.FileMultiSourceConversationRepository")
    @mock.patch("agent_builder_sdk.agent_factory.ConversationHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.MemoryHookProvider")
    @mock.patch("agent_builder_sdk.agent_factory.SubagentRegistryTools")
    @mock.patch("agent_builder_sdk.agent_factory.SendMessageTools")
    def test_prompt_caching_is_forwarded_and_off_by_default(self, *mocks):
        mock_orchestrator = mocks[-1]
        mock_orchestrator.return_value = mock.Mock()

        create_default_async_orchestrator_with_subagent(system_prompt="p")
        assert mock_orchestrator.call_args.kwargs["enable_prompt_caching"] is False

        create_default_async_orchestrator_with_subagent(
            system_prompt="p", enable_prompt_caching=True
        )
        assert mock_orchestrator.call_args.kwargs["enable_prompt_caching"] is True
