"""Tests for the MemoryHookProvider class."""

from unittest.mock import Mock, patch

import pytest
from strands.agent import Agent
from strands.hooks.events import MessageAddedEvent
from strands.hooks.registry import HookRegistry

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider import (
    MemoryHookProvider,
)


@pytest.fixture
def mock_memory_manager():
    """Create a mock memory manager."""
    return Mock(spec=MemoryManager)


@pytest.fixture
def hook_provider(mock_memory_manager):
    """Create a MemoryHookProvider instance."""
    return MemoryHookProvider(memory_manager=mock_memory_manager)


@pytest.fixture
def mock_registry():
    """Create a mock hook registry."""
    return Mock(spec=HookRegistry)


@pytest.fixture
def mock_agent():
    """Create a mock agent with messages."""
    agent = Mock(spec=Agent)
    agent.agent_id = "test-agent-id"
    agent.messages = []
    return agent


class TestMemoryHookProvider:
    """Test class for MemoryHookProvider."""

    def test_initialization(self, mock_memory_manager):
        """Test initialization with memory manager."""
        provider = MemoryHookProvider(memory_manager=mock_memory_manager)
        assert provider.memory_manager == mock_memory_manager

    def test_register_hooks(self, hook_provider, mock_registry):
        """Test hook registration."""
        hook_provider.register_hooks(mock_registry)

        # Verify MessageAddedEvent hook was registered
        mock_registry.add_callback.assert_called_once_with(
            MessageAddedEvent, hook_provider.retrieve_memories
        )

    def test_retrieve_memories_empty_messages(self, hook_provider, mock_agent):
        """Test retrieve_memories with empty messages list."""
        mock_agent.messages = []
        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Should not call memory manager when no messages
        hook_provider.memory_manager.get_context_for_message.assert_not_called()

    def test_retrieve_memories_non_user_message(self, hook_provider, mock_agent):
        """Test retrieve_memories with non-user message."""
        mock_agent.messages = [{"role": "assistant", "content": [{"text": "Assistant response"}]}]
        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Should not call memory manager for non-user messages
        hook_provider.memory_manager.get_context_for_message.assert_not_called()

    def test_retrieve_memories_tool_result_message(self, hook_provider, mock_agent):
        """Test retrieve_memories with tool result message."""
        mock_agent.messages = [
            {"role": "user", "content": [{"toolResult": "some result", "text": "User message"}]}
        ]
        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Should not call memory manager for tool result messages
        hook_provider.memory_manager.get_context_for_message.assert_not_called()

    def test_retrieve_memories_empty_text(self, hook_provider, mock_agent):
        """Test retrieve_memories with empty text content."""
        mock_agent.messages = [{"role": "user", "content": [{"text": ""}]}]
        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Should not call memory manager for empty text
        hook_provider.memory_manager.get_context_for_message.assert_not_called()

    def test_retrieve_memories_successful_retrieval(self, hook_provider, mock_agent):
        """Test successful memory retrieval and injection."""
        # Setup mock agent with user message
        mock_agent.messages = [
            {"role": "user", "content": [{"text": "Hello, what did we discuss?"}]}
        ]

        # Setup mock memory manager to return context
        hook_provider.memory_manager.get_context_for_message.return_value = (
            "Previous discussion about project planning"
        )

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify memory manager was called with correct parameters
        hook_provider.memory_manager.get_context_for_message.assert_called_once()
        call_args = hook_provider.memory_manager.get_context_for_message.call_args
        assert call_args[1]["message"] == "Hello, what did we discuss?"
        assert call_args[1]["limit"] == 5
        assert isinstance(call_args[1]["memory_context"], MemoryContext)

        # Verify message was updated with memory context
        expected_text = (
            "Hello, what did we discuss?\n\n"
            "Relevant context from memory: Previous discussion about project planning"
        )
        assert mock_agent.messages[0]["content"][0]["text"] == expected_text

    def test_retrieve_memories_no_context_returned(self, hook_provider, mock_agent):
        """Test memory retrieval when no context is returned."""
        # Setup mock agent with user message
        original_text = "Hello, what did we discuss?"
        mock_agent.messages = [{"role": "user", "content": [{"text": original_text}]}]

        # Setup mock memory manager to return empty context
        hook_provider.memory_manager.get_context_for_message.return_value = ""

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify memory manager was called
        hook_provider.memory_manager.get_context_for_message.assert_called_once()

        # Verify message was not modified when no context returned
        assert mock_agent.messages[0]["content"][0]["text"] == original_text

    def test_retrieve_memories_none_context_returned(self, hook_provider, mock_agent):
        """Test memory retrieval when None context is returned."""
        # Setup mock agent with user message
        original_text = "Hello, what did we discuss?"
        mock_agent.messages = [{"role": "user", "content": [{"text": original_text}]}]

        # Setup mock memory manager to return None
        hook_provider.memory_manager.get_context_for_message.return_value = None

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify memory manager was called
        hook_provider.memory_manager.get_context_for_message.assert_called_once()

        # Verify message was not modified when None returned
        assert mock_agent.messages[0]["content"][0]["text"] == original_text

    def test_retrieve_memories_exception_handling(self, hook_provider, mock_agent):
        """Test memory retrieval handles exceptions gracefully."""
        # Setup mock agent with user message
        original_text = "Hello, what did we discuss?"
        mock_agent.messages = [{"role": "user", "content": [{"text": original_text}]}]

        # Setup mock memory manager to raise exception
        hook_provider.memory_manager.get_context_for_message.side_effect = Exception("Memory error")

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        # Should not raise exception
        hook_provider.retrieve_memories(event)

        # Verify message was not modified when exception occurred
        assert mock_agent.messages[0]["content"][0]["text"] == original_text

    def test_retrieve_memories_creates_correct_context(self, hook_provider, mock_agent):
        """Test that retrieve_memories creates correct memory context."""
        # Setup mock agent with user message
        mock_agent.messages = [{"role": "user", "content": [{"text": "Test message"}]}]

        # Setup mock memory manager
        hook_provider.memory_manager.get_context_for_message.return_value = "Test context"

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify the memory context was created correctly
        call_args = hook_provider.memory_manager.get_context_for_message.call_args
        memory_context = call_args[1]["memory_context"]

        assert isinstance(memory_context, MemoryContext)
        assert isinstance(memory_context.conversation_context, ConversationContext)

    def test_retrieve_memories_with_multiple_messages(self, hook_provider, mock_agent):
        """Test retrieve_memories only processes the last message."""
        # Setup mock agent with multiple messages
        mock_agent.messages = [
            {"role": "user", "content": [{"text": "First message"}]},
            {"role": "assistant", "content": [{"text": "Assistant response"}]},
            {"role": "user", "content": [{"text": "Second message"}]},
        ]

        # Setup mock memory manager
        hook_provider.memory_manager.get_context_for_message.return_value = "Test context"

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify memory manager was called with the last message
        call_args = hook_provider.memory_manager.get_context_for_message.call_args
        assert call_args[1]["message"] == "Second message"

        # Verify only the last message was modified
        assert "Test context" in mock_agent.messages[2]["content"][0]["text"]
        assert "Test context" not in mock_agent.messages[0]["content"][0]["text"]

    @patch("agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider.logger")
    def test_retrieve_memories_logging(self, mock_logger, hook_provider, mock_agent):
        """Test that retrieve_memories logs appropriately."""
        # Setup mock agent with user message
        mock_agent.messages = [{"role": "user", "content": [{"text": "Test message"}]}]

        # Setup mock memory manager to return context
        hook_provider.memory_manager.get_context_for_message.return_value = "Test context"

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify success was logged
        mock_logger.info.assert_called_with("Retrieved and injected memory context")

    @patch("agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider.logger")
    def test_retrieve_memories_error_logging(self, mock_logger, hook_provider, mock_agent):
        """Test that retrieve_memories logs errors appropriately."""
        # Setup mock agent with user message
        mock_agent.messages = [{"role": "user", "content": [{"text": "Test message"}]}]

        # Setup mock memory manager to raise exception
        test_error = Exception("Memory error")
        hook_provider.memory_manager.get_context_for_message.side_effect = test_error

        event = MessageAddedEvent(message=Mock(), agent=mock_agent)

        hook_provider.retrieve_memories(event)

        # Verify error was logged
        mock_logger.error.assert_called_with(f"Failed to retrieve memories: {test_error}")

    @patch("agent_builder_sdk.orchestrator_strands.hooks.memory_hook_provider.logger")
    def test_register_hooks_logging(self, mock_logger, hook_provider, mock_registry):
        """Test that register_hooks logs appropriately."""
        hook_provider.register_hooks(mock_registry)

        # Verify registration was logged
        mock_logger.info.assert_called_with("Memory retrieval hook registered")


class TestMemoryHookProviderIntegration:
    """Integration tests for MemoryHookProvider."""

    def test_full_memory_retrieval_flow(self, mock_memory_manager):
        """Test the complete memory retrieval flow."""
        # Create provider
        provider = MemoryHookProvider(memory_manager=mock_memory_manager)

        # Setup mock agent
        mock_agent = Mock(spec=Agent)
        mock_agent.messages = [{"role": "user", "content": [{"text": "What did we discuss?"}]}]

        # Setup memory manager to return context
        mock_memory_manager.get_context_for_message.return_value = "Previous discussion"

        # Create event and call hook
        event = MessageAddedEvent(message=Mock(), agent=mock_agent)
        provider.retrieve_memories(event)

        # Verify the complete flow
        mock_memory_manager.get_context_for_message.assert_called_once()
        expected_text = (
            "What did we discuss?\n\n" "Relevant context from memory: Previous discussion"
        )
        assert mock_agent.messages[0]["content"][0]["text"] == expected_text
