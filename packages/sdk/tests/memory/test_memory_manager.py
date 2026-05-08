# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for memory_manager module.
"""

from unittest.mock import Mock

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_manager import MemoryManager
from agent_builder_sdk.memory.memory_types import MemoryTypeBase, MemoryTypeEnum


class MockMemoryType(MemoryTypeBase):
    """Mock memory type for testing."""

    def __init__(self, memory_type: MemoryTypeEnum):
        self._memory_type = memory_type
        self.store_mock = Mock()
        self.retrieve_mock = Mock()
        self.clear_mock = Mock()
        self.get_context_mock = Mock()

    @property
    def memory_type(self) -> MemoryTypeEnum:
        return self._memory_type

    def store(self, context, content, metadata=None):
        return self.store_mock(context, content, metadata)

    def retrieve(self, context, memory_id=None, limit=None):
        return self.retrieve_mock(context, memory_id, limit)

    def clear(self, context, memory_id=None):
        return self.clear_mock(context, memory_id)

    def get_context_for_message(self, message, memory_context, limit=5):
        return self.get_context_mock(message, memory_context, limit)


class TestMemoryManager:
    """Test cases for MemoryManager."""

    @pytest.fixture
    def conversation_context(self):
        """Create a test conversation context."""
        return ConversationContext(
            user_id="test_user", conversation_id="test_conversation", agent_instance_id="test_agent"
        )

    @pytest.fixture
    def memory_context(self, conversation_context):
        """Create a test memory context."""
        return MemoryContext(conversation_context=conversation_context)

    @pytest.fixture
    def mock_episodic_memory(self):
        """Create a mock episodic memory."""
        return MockMemoryType(MemoryTypeEnum.EPISODIC)

    def test_initialization_empty(self):
        """Test MemoryManager initialization with no memories."""
        manager = MemoryManager()

        assert manager.memories == {}

    def test_initialization_with_memories(self, mock_episodic_memory):
        """Test MemoryManager initialization with memories."""
        manager = MemoryManager([mock_episodic_memory])

        assert len(manager.memories) == 1
        assert MemoryTypeEnum.EPISODIC in manager.memories
        assert manager.memories[MemoryTypeEnum.EPISODIC] == mock_episodic_memory

    def test_initialization_with_multiple_memories(self):
        """Test MemoryManager initialization with multiple memory types."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)

        manager = MemoryManager([episodic_memory])

        assert len(manager.memories) == 1
        assert manager.memories[MemoryTypeEnum.EPISODIC] == episodic_memory

    def test_get_context_for_message_success(self, mock_episodic_memory, memory_context):
        """Test successful context retrieval for message."""
        mock_episodic_memory.get_context_mock.return_value = "Episodic context\n"

        manager = MemoryManager([mock_episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context, limit=10
        )

        assert result == "Episodic context\n"
        mock_episodic_memory.get_context_mock.assert_called_once_with(
            "test message", memory_context, 10
        )

    def test_get_context_for_message_multiple_memories(self, memory_context):
        """Test context retrieval with multiple memory types."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.get_context_mock.return_value = "Episodic context\n"

        manager = MemoryManager([episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == "Episodic context\n"

    def test_get_context_for_message_empty_context(self, mock_episodic_memory, memory_context):
        """Test context retrieval with empty context."""
        mock_episodic_memory.get_context_mock.return_value = ""

        manager = MemoryManager([mock_episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_get_context_for_message_no_memories(self, memory_context):
        """Test context retrieval with no configured memories."""
        manager = MemoryManager()

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_get_context_for_message_exception(self, mock_episodic_memory, memory_context):
        """Test context retrieval with exception."""
        mock_episodic_memory.get_context_mock.side_effect = Exception("Context error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_store_memory_enum_success(self, mock_episodic_memory, conversation_context):
        """Test successful memory storage with enum."""
        mock_episodic_memory.store_mock.return_value = "memory_id_123"

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            content="test content",
            metadata={"key": "value"},
        )

        assert result == "memory_id_123"
        mock_episodic_memory.store_mock.assert_called_once_with(
            conversation_context, "test content", {"key": "value"}
        )

    def test_store_memory_string_success(self, mock_episodic_memory, conversation_context):
        """Test successful memory storage with string."""
        mock_episodic_memory.store_mock.return_value = "memory_id_123"

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type="episodic", context=conversation_context, content="test content"
        )

        assert result == "memory_id_123"
        mock_episodic_memory.store_mock.assert_called_once_with(
            conversation_context, "test content", None
        )

    def test_store_memory_invalid_string(self, conversation_context):
        """Test memory storage with invalid string."""
        manager = MemoryManager()

        result = manager.store_memory(
            memory_type="invalid_type", context=conversation_context, content="test content"
        )

        assert result == ""

    def test_store_memory_unconfigured_type(self, conversation_context):
        """Test memory storage with unconfigured memory type."""
        manager = MemoryManager()

        result = manager.store_memory(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            content="test content",
        )

        assert result == ""

    def test_store_memory_exception(self, mock_episodic_memory, conversation_context):
        """Test memory storage with exception."""
        mock_episodic_memory.store_mock.side_effect = Exception("Store error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            content="test content",
        )

        assert result == ""

    def test_retrieve_memories_enum_success(self, mock_episodic_memory, conversation_context):
        """Test successful memory retrieval with enum."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_episodic_memory.retrieve_mock.return_value = expected_memories

        manager = MemoryManager([mock_episodic_memory])

        result = manager.retrieve_memories(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            memory_id="test_id",
            limit=10,
        )

        assert result == expected_memories
        mock_episodic_memory.retrieve_mock.assert_called_once_with(
            conversation_context, "test_id", 10
        )

    def test_retrieve_memories_string_success(self, mock_episodic_memory, conversation_context):
        """Test successful memory retrieval with string."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_episodic_memory.retrieve_mock.return_value = expected_memories

        manager = MemoryManager([mock_episodic_memory])

        result = manager.retrieve_memories(memory_type="episodic", context=conversation_context)

        assert result == expected_memories
        mock_episodic_memory.retrieve_mock.assert_called_once_with(conversation_context, None, None)

    def test_retrieve_memories_invalid_string(self, conversation_context):
        """Test memory retrieval with invalid string."""
        manager = MemoryManager()

        result = manager.retrieve_memories(memory_type="invalid_type", context=conversation_context)

        assert result == []

    def test_retrieve_memories_unconfigured_type(self, conversation_context):
        """Test memory retrieval with unconfigured memory type."""
        manager = MemoryManager()

        result = manager.retrieve_memories(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == []

    def test_retrieve_memories_exception(self, mock_episodic_memory, conversation_context):
        """Test memory retrieval with exception."""
        mock_episodic_memory.retrieve_mock.side_effect = Exception("Retrieve error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.retrieve_memories(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == []

    def test_clear_memory_specific_type(self, mock_episodic_memory, conversation_context):
        """Test clearing specific memory type."""
        mock_episodic_memory.clear_mock.return_value = 5

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == 5
        mock_episodic_memory.clear_mock.assert_called_once_with(conversation_context, None)

    def test_clear_memory_specific_type_string(self, mock_episodic_memory, conversation_context):
        """Test clearing specific memory type with string."""
        mock_episodic_memory.clear_mock.return_value = 3

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(memory_type="episodic", context=conversation_context)

        assert result == 3

    def test_clear_memory_all_types(self, mock_episodic_memory, conversation_context):
        """Test clearing all memory types."""
        mock_episodic_memory.clear_mock.return_value = 5

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(context=conversation_context)

        assert result == 5
        mock_episodic_memory.clear_mock.assert_called_once_with(conversation_context, None)

    def test_clear_memory_no_context(self, mock_episodic_memory):
        """Test clearing memory without context."""
        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(memory_type=MemoryTypeEnum.EPISODIC)

        assert result == 0
        mock_episodic_memory.clear_mock.assert_not_called()

    def test_clear_memory_invalid_string(self, conversation_context):
        """Test clearing memory with invalid string."""
        manager = MemoryManager()

        result = manager.clear_memory(memory_type="invalid_type", context=conversation_context)

        assert result == 0

    def test_clear_memory_unconfigured_type(self, conversation_context):
        """Test clearing unconfigured memory type."""
        manager = MemoryManager()

        result = manager.clear_memory(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == 0

    def test_clear_memory_exception(self, mock_episodic_memory, conversation_context):
        """Test clearing memory with exception."""
        mock_episodic_memory.clear_mock.side_effect = Exception("Clear error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == 0

    def test_get_context_for_message_with_multiple_memory_types(self, memory_context):
        """Test context retrieval with multiple memory types returning context."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.get_context_mock.return_value = "Episodic context\n"

        manager = MemoryManager([episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context, limit=8
        )

        assert result == "Episodic context\n"
        episodic_memory.get_context_mock.assert_called_once_with("test message", memory_context, 8)

    def test_get_context_for_message_combines_multiple_contexts(self, memory_context):
        """Test that multiple memory type contexts are combined correctly."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.get_context_mock.return_value = "Episodic context"

        manager = MemoryManager([episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == "Episodic context"

    def test_get_context_for_message_filters_empty_contexts(self, memory_context):
        """Test that empty contexts are filtered out."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.get_context_mock.return_value = ""  # Empty context

        manager = MemoryManager([episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_store_memory_with_enum_and_metadata(self, mock_episodic_memory, conversation_context):
        """Test store_memory with enum type and metadata."""
        mock_episodic_memory.store_mock.return_value = "stored_id"

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            content="test content",
            metadata={"test": True, "number": 42},
        )

        assert result == "stored_id"
        mock_episodic_memory.store_mock.assert_called_once_with(
            conversation_context, "test content", {"test": True, "number": 42}
        )

    def test_store_memory_string_to_enum_conversion(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that string memory types are converted to enums."""
        mock_episodic_memory.store_mock.return_value = "converted_id"

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type="episodic",  # String instead of enum
            context=conversation_context,
            content="test content",
        )

        assert result == "converted_id"
        mock_episodic_memory.store_mock.assert_called_once_with(
            conversation_context, "test content", None
        )

    def test_retrieve_memories_string_to_enum_conversion(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that string memory types are converted to enums in retrieve."""
        expected_memories = [{"id": "test"}]
        mock_episodic_memory.retrieve_mock.return_value = expected_memories

        manager = MemoryManager([mock_episodic_memory])

        result = manager.retrieve_memories(
            memory_type="episodic",  # String instead of enum
            context=conversation_context,
            memory_id="test_id",
            limit=5,
        )

        assert result == expected_memories
        mock_episodic_memory.retrieve_mock.assert_called_once_with(
            conversation_context, "test_id", 5
        )

    def test_clear_memory_string_to_enum_conversion(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that string memory types are converted to enums in clear."""
        mock_episodic_memory.clear_mock.return_value = 7

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(
            memory_type="episodic", context=conversation_context  # String instead of enum
        )

        assert result == 7
        mock_episodic_memory.clear_mock.assert_called_once_with(conversation_context, None)

    def test_clear_memory_all_types_with_multiple_memories(self, conversation_context):
        """Test clearing all memory types when multiple are configured."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.clear_mock.return_value = 5

        manager = MemoryManager([episodic_memory])

        result = manager.clear_memory(context=conversation_context)

        assert result == 5
        episodic_memory.clear_mock.assert_called_once_with(conversation_context, None)

    def test_clear_memory_specific_type_without_context_warning(self, mock_episodic_memory):
        """Test that clearing specific type without context logs warning and returns 0."""
        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(
            memory_type=MemoryTypeEnum.EPISODIC
            # No context provided
        )

        assert result == 0
        mock_episodic_memory.clear_mock.assert_not_called()

    def test_clear_memory_all_types_without_context_warning(self, mock_episodic_memory):
        """Test that clearing all types without context logs warning and returns 0."""
        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory()  # No memory_type or context

        assert result == 0
        mock_episodic_memory.clear_mock.assert_not_called()

    def test_store_memory_repository_exception_handling(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that store_memory handles repository exceptions gracefully."""
        mock_episodic_memory.store_mock.side_effect = RuntimeError("Repository error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.store_memory(
            memory_type=MemoryTypeEnum.EPISODIC,
            context=conversation_context,
            content="test content",
        )

        assert result == ""

    def test_retrieve_memories_repository_exception_handling(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that retrieve_memories handles repository exceptions gracefully."""
        mock_episodic_memory.retrieve_mock.side_effect = RuntimeError("Repository error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.retrieve_memories(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == []

    def test_clear_memory_repository_exception_handling(
        self, mock_episodic_memory, conversation_context
    ):
        """Test that clear_memory handles repository exceptions gracefully."""
        mock_episodic_memory.clear_mock.side_effect = RuntimeError("Repository error")

        manager = MemoryManager([mock_episodic_memory])

        result = manager.clear_memory(
            memory_type=MemoryTypeEnum.EPISODIC, context=conversation_context
        )

        assert result == 0

    def test_get_context_memory_exception_handling(self, memory_context):
        """Test that get_context_for_message handles memory exceptions gracefully."""
        episodic_memory = MockMemoryType(MemoryTypeEnum.EPISODIC)
        episodic_memory.get_context_mock.side_effect = RuntimeError("Memory error")

        manager = MemoryManager([episodic_memory])

        result = manager.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""
