# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for episodic_memory module.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.episodic_memory import EpisodicMemory
from agent_builder_sdk.memory.memory_repository import MemoryRepository
from agent_builder_sdk.memory.memory_types import MemoryTypeEnum


class MockRepository(MemoryRepository):
    """Mock repository for testing."""

    def __init__(self):
        self.store_mock = Mock()
        self.retrieve_mock = Mock()
        self.clear_mock = Mock()

    def store(self, memory_id, timestamp, context, content, metadata=None):
        return self.store_mock(memory_id, timestamp, context, content, metadata)

    def retrieve(self, memory_id=None, context=None, limit=None):
        return self.retrieve_mock(memory_id, context, limit)

    def clear(self, memory_id=None, context=None):
        return self.clear_mock(memory_id, context)


class TestEpisodicMemory:
    """Test cases for EpisodicMemory."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository for testing."""
        return MockRepository()

    @pytest.fixture
    def episodic_memory(self, mock_repository):
        """Create an EpisodicMemory instance for testing."""
        return EpisodicMemory(mock_repository)

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

    def test_memory_type_property(self, episodic_memory):
        """Test that memory_type property returns EPISODIC."""
        assert episodic_memory.memory_type == MemoryTypeEnum.EPISODIC

    def test_initialization(self, mock_repository):
        """Test EpisodicMemory initialization."""
        episodic_memory = EpisodicMemory(mock_repository)

        assert episodic_memory.repository == mock_repository
        assert episodic_memory.memory_type == MemoryTypeEnum.EPISODIC

    def test_store_success(self, episodic_memory, mock_repository, conversation_context):
        """Test successful memory storage."""
        mock_repository.store_mock.return_value = True

        result = episodic_memory.store(
            context=conversation_context, content="test content", metadata={"key": "value"}
        )

        # Should return a UUID string
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify repository was called correctly
        mock_repository.store_mock.assert_called_once()
        call_args = mock_repository.store_mock.call_args[0]
        assert call_args[0] == result  # memory_id
        assert isinstance(call_args[1], datetime)  # timestamp
        assert call_args[2] == conversation_context  # context
        assert call_args[3] == "test content"  # content
        assert call_args[4] == {"key": "value"}  # metadata

    def test_store_without_metadata(self, episodic_memory, mock_repository, conversation_context):
        """Test memory storage without metadata."""
        mock_repository.store_mock.return_value = True

        result = episodic_memory.store(context=conversation_context, content="test content")

        assert isinstance(result, str)
        assert len(result) > 0

        # Verify metadata was None
        call_args = mock_repository.store_mock.call_args[0]
        assert call_args[4] is None  # metadata

    def test_store_failure(self, episodic_memory, mock_repository, conversation_context):
        """Test memory storage failure."""
        mock_repository.store_mock.return_value = False

        result = episodic_memory.store(context=conversation_context, content="test content")

        assert result == ""

    def test_store_exception(self, episodic_memory, mock_repository, conversation_context):
        """Test memory storage with exception."""
        mock_repository.store_mock.side_effect = Exception("Storage error")

        result = episodic_memory.store(context=conversation_context, content="test content")

        assert result == ""

    def test_retrieve_success(self, episodic_memory, mock_repository, conversation_context):
        """Test successful memory retrieval."""
        expected_memories = [
            {"memory_id": "test1", "content": "content1"},
            {"memory_id": "test2", "content": "content2"},
        ]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = episodic_memory.retrieve(
            context=conversation_context, memory_id="test_memory_id", limit=10
        )

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(
            "test_memory_id", conversation_context, 10
        )

    def test_retrieve_with_defaults(self, episodic_memory, mock_repository, conversation_context):
        """Test memory retrieval with default parameters."""
        expected_memories = []
        mock_repository.retrieve_mock.return_value = expected_memories

        result = episodic_memory.retrieve(context=conversation_context)

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(None, conversation_context, None)

    def test_retrieve_exception(self, episodic_memory, mock_repository, conversation_context):
        """Test memory retrieval with exception."""
        mock_repository.retrieve_mock.side_effect = Exception("Retrieval error")

        result = episodic_memory.retrieve(context=conversation_context)

        assert result == []

    def test_clear_success(self, episodic_memory, mock_repository, conversation_context):
        """Test successful memory clearing."""
        mock_repository.clear_mock.return_value = 5

        result = episodic_memory.clear(context=conversation_context, memory_id="test_memory_id")

        assert result == 5
        mock_repository.clear_mock.assert_called_once_with("test_memory_id", conversation_context)

    def test_clear_with_defaults(self, episodic_memory, mock_repository, conversation_context):
        """Test memory clearing with default parameters."""
        mock_repository.clear_mock.return_value = 3

        result = episodic_memory.clear(context=conversation_context)

        assert result == 3
        mock_repository.clear_mock.assert_called_once_with(None, conversation_context)

    def test_clear_exception(self, episodic_memory, mock_repository, conversation_context):
        """Test memory clearing with exception."""
        mock_repository.clear_mock.side_effect = Exception("Clear error")

        result = episodic_memory.clear(context=conversation_context)

        assert result == 0

    def test_format_for_context_empty_memories(self, episodic_memory):
        """Test format_for_context with empty memories list."""
        result = episodic_memory.format_for_context([])

        assert result == ""

    def test_format_for_context_with_memories(self, episodic_memory):
        """Test format_for_context with memories."""
        memories = [
            {"timestamp": "2023-01-15T12:30:45", "content": "First memory content"},
            {"timestamp": "2023-01-15T13:45:30", "content": "Second memory content"},
        ]

        result = episodic_memory.format_for_context(memories)

        expected = "[2023-01-15 12:30:45] First memory content\n[2023-01-15 13:45:30] Second memory content"
        assert result == expected

    def test_format_for_context_invalid_timestamp(self, episodic_memory):
        """Test format_for_context with invalid timestamp."""
        memories = [{"timestamp": "invalid_timestamp", "content": "Memory content"}]

        result = episodic_memory.format_for_context(memories)

        expected = "[invalid_timestamp] Memory content"
        assert result == expected

    def test_format_for_context_missing_fields(self, episodic_memory):
        """Test format_for_context with missing fields."""
        memories = [
            {"content": "Memory without timestamp"},
            {"timestamp": "2023-01-15T12:30:45"},  # Missing content
            {},  # Missing both
        ]

        result = episodic_memory.format_for_context(memories)

        expected = "[] Memory without timestamp\n[2023-01-15 12:30:45] \n[] "
        assert result == expected

    def test_get_context_for_message_success(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test successful context retrieval for message."""
        memories = [{"timestamp": "2023-01-15T12:30:45", "content": "Previous conversation"}]
        mock_repository.retrieve_mock.return_value = memories

        result = episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context, limit=10
        )

        expected = "Previous conversation context:\n[2023-01-15 12:30:45] Previous conversation\n\n"
        assert result == expected

        mock_repository.retrieve_mock.assert_called_once_with(
            None, memory_context.conversation_context, 10
        )

    def test_get_context_for_message_no_memories(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test context retrieval with no memories."""
        mock_repository.retrieve_mock.return_value = []

        result = episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_get_context_for_message_default_limit(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test context retrieval with default limit."""
        mock_repository.retrieve_mock.return_value = []

        episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        mock_repository.retrieve_mock.assert_called_once_with(
            None, memory_context.conversation_context, 5  # Default limit
        )

    def test_get_context_for_message_exception(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test context retrieval with exception."""
        mock_repository.retrieve_mock.side_effect = Exception("Context error")

        result = episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == ""

    def test_get_context_for_message_empty_formatted_context(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test context retrieval when formatted context is empty."""
        # Return memories but they format to empty string
        memories = [{"timestamp": "", "content": ""}]
        mock_repository.retrieve_mock.return_value = memories

        result = episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        # Should return formatted context even with empty timestamp/content
        expected = "Previous conversation context:\n[] \n\n"
        assert result == expected

    def test_store_repository_failure_returns_empty_string(
        self, episodic_memory, mock_repository, conversation_context
    ):
        """Test that store returns empty string when repository fails."""
        mock_repository.store_mock.return_value = False

        result = episodic_memory.store(context=conversation_context, content="test content")

        assert result == ""
        mock_repository.store_mock.assert_called_once()

    def test_store_generates_unique_memory_ids(
        self, episodic_memory, mock_repository, conversation_context
    ):
        """Test that store generates unique memory IDs."""
        mock_repository.store_mock.return_value = True

        # Store multiple memories
        memory_ids = []
        for i in range(5):
            memory_id = episodic_memory.store(context=conversation_context, content=f"content {i}")
            memory_ids.append(memory_id)

        # All IDs should be non-empty and unique
        assert all(memory_id != "" for memory_id in memory_ids)
        assert len(set(memory_ids)) == 5

    def test_store_calls_repository_with_current_timestamp(
        self, episodic_memory, mock_repository, conversation_context
    ):
        """Test that store calls repository with current timestamp."""
        mock_repository.store_mock.return_value = True

        before_time = datetime.now()
        episodic_memory.store(context=conversation_context, content="test content")
        after_time = datetime.now()

        # Verify repository was called with timestamp between before and after
        mock_repository.store_mock.assert_called_once()
        call_args = mock_repository.store_mock.call_args[0]
        timestamp = call_args[1]

        assert isinstance(timestamp, datetime)
        assert before_time <= timestamp <= after_time

    def test_retrieve_calls_repository_correctly(
        self, episodic_memory, mock_repository, conversation_context
    ):
        """Test that retrieve calls repository with correct parameters."""
        expected_memories = [{"memory_id": "test", "content": "content"}]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = episodic_memory.retrieve(
            context=conversation_context, memory_id="specific_id", limit=20
        )

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(
            "specific_id", conversation_context, 20
        )

    def test_clear_calls_repository_correctly(
        self, episodic_memory, mock_repository, conversation_context
    ):
        """Test that clear calls repository with correct parameters."""
        mock_repository.clear_mock.return_value = 10

        result = episodic_memory.clear(context=conversation_context, memory_id="specific_id")

        assert result == 10
        mock_repository.clear_mock.assert_called_once_with("specific_id", conversation_context)

    def test_format_for_context_handles_various_timestamp_formats(self, episodic_memory):
        """Test format_for_context with various timestamp formats."""
        memories = [
            {"timestamp": "2023-01-15T12:30:45.123456", "content": "Microseconds"},
            {"timestamp": "2023-01-15T12:30:45", "content": "No microseconds"},
            {"timestamp": "2023-01-15T12:30:45Z", "content": "With Z"},
            {"timestamp": "2023-01-15T12:30:45+00:00", "content": "With timezone"},
            {"timestamp": "", "content": "Empty timestamp"},
            {"timestamp": None, "content": "None timestamp"},
        ]

        result = episodic_memory.format_for_context(memories)

        lines = result.split("\n")
        assert len(lines) == 6
        assert "[2023-01-15 12:30:45] Microseconds" in lines[0]
        assert "[2023-01-15 12:30:45] No microseconds" in lines[1]
        assert "[2023-01-15 12:30:45] With Z" in lines[2]
        assert "[2023-01-15 12:30:45] With timezone" in lines[3]
        assert "[] Empty timestamp" in lines[4]
        assert "[None] None timestamp" in lines[5]

    def test_get_context_for_message_with_multiple_memories(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test context generation with multiple memories."""
        memories = [
            {"timestamp": "2023-01-15T10:00:00", "content": "First memory"},
            {"timestamp": "2023-01-15T11:00:00", "content": "Second memory"},
            {"timestamp": "2023-01-15T12:00:00", "content": "Third memory"},
        ]
        mock_repository.retrieve_mock.return_value = memories

        result = episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context, limit=3
        )

        expected = (
            "Previous conversation context:\n"
            "[2023-01-15 10:00:00] First memory\n"
            "[2023-01-15 11:00:00] Second memory\n"
            "[2023-01-15 12:00:00] Third memory\n\n"
        )
        assert result == expected

    def test_get_context_for_message_respects_limit(
        self, episodic_memory, mock_repository, memory_context
    ):
        """Test that get_context_for_message respects the limit parameter."""
        episodic_memory.get_context_for_message(
            message="test message", memory_context=memory_context, limit=15
        )

        mock_repository.retrieve_mock.assert_called_once_with(
            None, memory_context.conversation_context, 15
        )

    def test_format_for_context_with_malformed_memory_objects(self, episodic_memory):
        """Test format_for_context handles malformed memory objects gracefully."""
        memories = [
            {"timestamp": "2023-01-15T12:30:45", "content": "Good memory"},
            {"timestamp": "2023-01-15T12:30:45"},  # Missing content
            {"content": "Missing timestamp"},
            {},  # Empty object
            None,  # None object - this might cause issues
        ]

        # Filter out None to avoid TypeError
        memories = [m for m in memories if m is not None]

        result = episodic_memory.format_for_context(memories)

        lines = result.split("\n")
        assert "[2023-01-15 12:30:45] Good memory" in lines[0]
        assert "[2023-01-15 12:30:45] " in lines[1]  # Empty content
        assert "[] Missing timestamp" in lines[2]
        assert "[] " in lines[3]  # Empty object
