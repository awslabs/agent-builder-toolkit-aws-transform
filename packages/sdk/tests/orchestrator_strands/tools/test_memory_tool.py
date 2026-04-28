"""Tests for the MemoryTool class."""

from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.memory.memory_types import MemoryTypeEnum
from agent_builder_sdk.orchestrator_strands.tools.memory_tool import MemoryTool


@pytest.fixture
def mock_memory_manager():
    """Create a mock memory manager."""
    return Mock(spec=MemoryManager)


@pytest.fixture
def memory_tool(mock_memory_manager):
    """Create a MemoryTool instance."""
    return MemoryTool(memory_manager=mock_memory_manager)


class TestMemoryTool:
    """Test class for MemoryTool."""

    def test_initialization(self, mock_memory_manager):
        """Test MemoryTool initialization."""
        tool = MemoryTool(memory_manager=mock_memory_manager)
        assert tool.memory_manager == mock_memory_manager

    @pytest.mark.asyncio
    async def test_store_operation_success(self, memory_tool):
        """Test successful store operation."""
        # Setup mock memory manager to return a memory ID
        memory_tool.memory_manager.store_memory.return_value = "memory-123"

        # Call the tool
        result = await memory_tool.memory(operation="store", content="Test memory content")

        # Verify memory manager was called correctly
        memory_tool.memory_manager.store_memory.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            content="Test memory content",
        )

        # Verify result
        assert isinstance(result, str)
        assert "Successfully stored memory: Test memory content" in result

    @pytest.mark.asyncio
    async def test_store_operation_long_content_preview(self, memory_tool):
        """Test store operation with long content shows preview."""
        # Setup mock memory manager to return a memory ID
        memory_tool.memory_manager.store_memory.return_value = "memory-123"

        # Create long content
        long_content = "A" * 100  # 100 characters

        # Call the tool
        result = await memory_tool.memory(operation="store", content=long_content)

        # Verify result shows preview
        assert isinstance(result, str)
        expected_preview = "A" * 50 + "..."
        assert f"Successfully stored memory: {expected_preview}" in result

    @pytest.mark.asyncio
    async def test_store_operation_empty_content(self, memory_tool):
        """Test store operation with empty content."""
        # Call the tool with empty content
        result = await memory_tool.memory(operation="store", content="")

        # Verify memory manager was not called
        memory_tool.memory_manager.store_memory.assert_not_called()

        # Verify error result
        assert isinstance(result, str)
        assert "Content is required for store operation" in result

    @pytest.mark.asyncio
    async def test_store_operation_whitespace_content(self, memory_tool):
        """Test store operation with whitespace-only content."""
        # Call the tool with whitespace content
        result = await memory_tool.memory(operation="store", content="   \n\t  ")

        # Verify memory manager was not called
        memory_tool.memory_manager.store_memory.assert_not_called()

        # Verify error result
        assert isinstance(result, str)
        assert "Content is required for store operation" in result

    @pytest.mark.asyncio
    async def test_store_operation_none_content(self, memory_tool):
        """Test store operation with None content."""
        # Call the tool with None content
        result = await memory_tool.memory(operation="store", content=None)

        # Verify memory manager was not called
        memory_tool.memory_manager.store_memory.assert_not_called()

        # Verify error result
        assert isinstance(result, str)
        assert "Content is required for store operation" in result

    @pytest.mark.asyncio
    async def test_store_operation_failure(self, memory_tool):
        """Test store operation when memory manager returns None."""
        # Setup mock memory manager to return None (failure)
        memory_tool.memory_manager.store_memory.return_value = None

        # Call the tool
        result = await memory_tool.memory(operation="store", content="Test content")

        # Verify error result
        assert isinstance(result, str)
        assert "Failed to store memory" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_success(self, memory_tool):
        """Test successful retrieve operation."""
        # Setup mock memory manager to return memories
        mock_memories = [
            {"content": "First memory", "timestamp": "2023-01-01T10:00:00Z"},
            {"content": "Second memory", "timestamp": "2023-01-01T11:00:00Z"},
        ]
        memory_tool.memory_manager.retrieve_memories.return_value = mock_memories

        # Call the tool
        result = await memory_tool.memory(operation="retrieve", limit=5)

        # Verify memory manager was called correctly
        memory_tool.memory_manager.retrieve_memories.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            limit=5,
        )

        # Verify result
        assert isinstance(result, str)
        assert "Retrieved 2 memories:" in result
        assert "1. [2023-01-01T10:00:00Z] First memory" in result
        assert "2. [2023-01-01T11:00:00Z] Second memory" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_default_limit(self, memory_tool):
        """Test retrieve operation with default limit."""
        # Setup mock memory manager
        memory_tool.memory_manager.retrieve_memories.return_value = []

        # Call the tool without limit parameter
        result = await memory_tool.memory(operation="retrieve")

        # Verify memory manager was called with default limit
        memory_tool.memory_manager.retrieve_memories.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            limit=10,
        )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_retrieve_operation_custom_limit(self, memory_tool):
        """Test retrieve operation with custom limit."""
        # Setup mock memory manager
        memory_tool.memory_manager.retrieve_memories.return_value = []

        # Call the tool with custom limit
        result = await memory_tool.memory(operation="retrieve", limit=20)

        # Verify memory manager was called with custom limit
        memory_tool.memory_manager.retrieve_memories.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            limit=20,
        )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_retrieve_operation_no_memories(self, memory_tool):
        """Test retrieve operation when no memories are found."""
        # Setup mock memory manager to return empty list
        memory_tool.memory_manager.retrieve_memories.return_value = []

        # Call the tool
        result = await memory_tool.memory(operation="retrieve")

        # Verify result
        assert isinstance(result, str)
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_none_memories(self, memory_tool):
        """Test retrieve operation when memory manager returns None."""
        # Setup mock memory manager to return None
        memory_tool.memory_manager.retrieve_memories.return_value = None

        # Call the tool
        result = await memory_tool.memory(operation="retrieve")

        # Verify result
        assert isinstance(result, str)
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_memories_without_timestamp(self, memory_tool):
        """Test retrieve operation with memories missing timestamp."""
        # Setup mock memory manager to return memories without timestamp
        mock_memories = [
            {"content": "Memory without timestamp"},
            {"content": "Another memory", "timestamp": "2023-01-01T10:00:00Z"},
        ]
        memory_tool.memory_manager.retrieve_memories.return_value = mock_memories

        # Call the tool
        result = await memory_tool.memory(operation="retrieve")

        # Verify result handles missing timestamp gracefully
        assert isinstance(result, str)
        assert "1. [] Memory without timestamp" in result
        assert "2. [2023-01-01T10:00:00Z] Another memory" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_memories_without_content(self, memory_tool):
        """Test retrieve operation with memories missing content."""
        # Setup mock memory manager to return memories without content
        mock_memories = [
            {"timestamp": "2023-01-01T10:00:00Z"},
            {"content": "Valid memory", "timestamp": "2023-01-01T11:00:00Z"},
        ]
        memory_tool.memory_manager.retrieve_memories.return_value = mock_memories

        # Call the tool
        result = await memory_tool.memory(operation="retrieve")

        # Verify result handles missing content gracefully
        assert isinstance(result, str)
        assert "1. [2023-01-01T10:00:00Z] " in result
        assert "2. [2023-01-01T11:00:00Z] Valid memory" in result

    @pytest.mark.asyncio
    async def test_unknown_operation(self, memory_tool):
        """Test unknown operation."""
        # Call the tool with unknown operation
        result = await memory_tool.memory(operation="unknown")

        # Verify memory manager was not called
        memory_tool.memory_manager.store_memory.assert_not_called()
        memory_tool.memory_manager.retrieve_memories.assert_not_called()

        # Verify error result
        assert isinstance(result, str)
        assert "Unknown operation 'unknown'" in result
        assert "Use 'store' or 'retrieve'" in result

    @pytest.mark.asyncio
    async def test_store_operation_exception(self, memory_tool):
        """Test store operation when memory manager raises exception."""
        # Setup mock memory manager to raise exception
        memory_tool.memory_manager.store_memory.side_effect = Exception("Storage error")

        # Call the tool
        result = await memory_tool.memory(operation="store", content="Test content")

        # Verify error result
        assert isinstance(result, str)
        assert "Memory operation failed: Storage error" in result

    @pytest.mark.asyncio
    async def test_retrieve_operation_exception(self, memory_tool):
        """Test retrieve operation when memory manager raises exception."""
        # Setup mock memory manager to raise exception
        memory_tool.memory_manager.retrieve_memories.side_effect = Exception("Retrieval error")

        # Call the tool
        result = await memory_tool.memory(operation="retrieve")

        # Verify error result
        assert isinstance(result, str)
        assert "Memory operation failed: Retrieval error" in result

    @pytest.mark.asyncio
    async def test_conversation_context_creation(self, memory_tool):
        """Test that ConversationContext is created correctly."""
        # Setup mock memory manager
        memory_tool.memory_manager.store_memory.return_value = "memory-123"

        # Call the tool
        await memory_tool.memory(operation="store", content="Test content")

        # Verify ConversationContext was passed correctly
        call_args = memory_tool.memory_manager.store_memory.call_args
        context = call_args[1]["context"]
        assert isinstance(context, ConversationContext)

    @patch("agent_builder_sdk.orchestrator_strands.tools.memory_tool.logger")
    def test_initialization_logging(self, mock_logger, mock_memory_manager):
        """Test that initialization logs appropriately."""
        MemoryTool(memory_manager=mock_memory_manager)

        # Verify initialization was logged
        mock_logger.info.assert_called_with("Initialized MemoryTool")

    @patch("agent_builder_sdk.orchestrator_strands.tools.memory_tool.logger")
    @pytest.mark.asyncio
    async def test_exception_logging(self, mock_logger, memory_tool):
        """Test that exceptions are logged appropriately."""
        # Setup mock memory manager to raise exception
        test_error = Exception("Test error")
        memory_tool.memory_manager.store_memory.side_effect = test_error

        # Call the tool
        await memory_tool.memory(operation="store", content="Test content")

        # Verify error was logged
        mock_logger.error.assert_called_with(f"Memory operation error: {test_error}")


class TestMemoryToolIntegration:
    """Integration tests for MemoryTool."""

    @pytest.mark.asyncio
    async def test_full_store_retrieve_flow(self, mock_memory_manager):
        """Test the complete store and retrieve flow."""
        # Create tool
        tool = MemoryTool(memory_manager=mock_memory_manager)

        # Setup mock memory manager for store
        mock_memory_manager.store_memory.return_value = "memory-123"

        # Store a memory
        store_result = await tool.memory(operation="store", content="Important information")

        # Verify store was successful
        assert isinstance(store_result, str)
        assert "Successfully stored memory" in store_result
        mock_memory_manager.store_memory.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            content="Important information",
        )

        # Setup mock memory manager for retrieve
        mock_memories = [{"content": "Important information", "timestamp": "2023-01-01T10:00:00Z"}]
        mock_memory_manager.retrieve_memories.return_value = mock_memories

        # Retrieve memories
        retrieve_result = await tool.memory(operation="retrieve")

        # Verify retrieve was successful
        assert isinstance(retrieve_result, str)
        assert "Important information" in retrieve_result
        mock_memory_manager.retrieve_memories.assert_called_once_with(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=ConversationContext(),
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_tool_decorator_functionality(self, mock_memory_manager):
        """Test that the @tool decorator works correctly."""
        # Create tool
        tool = MemoryTool(memory_manager=mock_memory_manager)

        # Verify the memory method has tool attributes
        assert hasattr(tool.memory, "__wrapped__")
        assert callable(tool.memory)

        # Verify we can call it as an async function
        mock_memory_manager.retrieve_memories.return_value = []
        result = await tool.memory(operation="retrieve")
        assert isinstance(result, str)
