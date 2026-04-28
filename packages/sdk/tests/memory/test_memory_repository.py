"""
Unit tests for repository module.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext
from agent_builder_sdk.memory.memory_repository import MemoryRepository


class MockMemoryRepository(MemoryRepository):
    """Mock implementation of MemoryRepository for testing."""

    def __init__(self):
        self.store_mock = Mock()
        self.retrieve_mock = Mock()
        self.clear_mock = Mock()

    def store(
        self,
        memory_id: str,
        timestamp: datetime,
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.store_mock(memory_id, timestamp, context, content, metadata)

    def retrieve(
        self,
        memory_id: Optional[str] = None,
        context: Optional[ConversationContext] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.retrieve_mock(memory_id, context, limit)

    def clear(
        self,
        memory_id: Optional[str] = None,
        context: Optional[ConversationContext] = None,
    ) -> int:
        return self.clear_mock(memory_id, context)


class TestMemoryRepository:
    """Test cases for MemoryRepository abstract class."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository for testing."""
        return MockMemoryRepository()

    @pytest.fixture
    def conversation_context(self):
        """Create a test conversation context."""
        return ConversationContext(
            user_id="test_user", conversation_id="test_conversation", agent_instance_id="test_agent"
        )

    @pytest.fixture
    def test_timestamp(self):
        """Create a test timestamp."""
        return datetime(2023, 1, 1, 12, 0, 0)

    def test_store_method_signature(self, mock_repository, conversation_context, test_timestamp):
        """Test store method can be called with expected parameters."""
        mock_repository.store_mock.return_value = True

        result = mock_repository.store(
            memory_id="test_memory_id",
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
            metadata={"key": "value"},
        )

        assert result is True
        mock_repository.store_mock.assert_called_once_with(
            "test_memory_id", test_timestamp, conversation_context, "test content", {"key": "value"}
        )

    def test_store_method_without_metadata(
        self, mock_repository, conversation_context, test_timestamp
    ):
        """Test store method works without metadata."""
        mock_repository.store_mock.return_value = True

        result = mock_repository.store(
            memory_id="test_memory_id",
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        assert result is True
        mock_repository.store_mock.assert_called_once_with(
            "test_memory_id", test_timestamp, conversation_context, "test content", None
        )

    def test_store_method_returns_false_on_failure(
        self, mock_repository, conversation_context, test_timestamp
    ):
        """Test store method can return False on failure."""
        mock_repository.store_mock.return_value = False

        result = mock_repository.store(
            memory_id="test_memory_id",
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        assert result is False

    def test_retrieve_method_with_memory_id(self, mock_repository):
        """Test retrieve method with memory_id parameter."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = mock_repository.retrieve(memory_id="test_memory_id")

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with("test_memory_id", None, None)

    def test_retrieve_method_with_context(self, mock_repository, conversation_context):
        """Test retrieve method with context parameter."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = mock_repository.retrieve(context=conversation_context)

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(None, conversation_context, None)

    def test_retrieve_method_with_limit(self, mock_repository, conversation_context):
        """Test retrieve method with limit parameter."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = mock_repository.retrieve(context=conversation_context, limit=10)

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(None, conversation_context, 10)

    def test_retrieve_method_with_all_parameters(self, mock_repository, conversation_context):
        """Test retrieve method with all parameters."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_repository.retrieve_mock.return_value = expected_memories

        result = mock_repository.retrieve(
            memory_id="test_memory_id", context=conversation_context, limit=5
        )

        assert result == expected_memories
        mock_repository.retrieve_mock.assert_called_once_with(
            "test_memory_id", conversation_context, 5
        )

    def test_retrieve_method_returns_empty_list(self, mock_repository):
        """Test retrieve method can return empty list."""
        mock_repository.retrieve_mock.return_value = []

        result = mock_repository.retrieve()

        assert result == []
        mock_repository.retrieve_mock.assert_called_once_with(None, None, None)

    def test_clear_method_with_memory_id(self, mock_repository):
        """Test clear method with memory_id parameter."""
        mock_repository.clear_mock.return_value = 1

        result = mock_repository.clear(memory_id="test_memory_id")

        assert result == 1
        mock_repository.clear_mock.assert_called_once_with("test_memory_id", None)

    def test_clear_method_with_context(self, mock_repository, conversation_context):
        """Test clear method with context parameter."""
        mock_repository.clear_mock.return_value = 5

        result = mock_repository.clear(context=conversation_context)

        assert result == 5
        mock_repository.clear_mock.assert_called_once_with(None, conversation_context)

    def test_clear_method_with_all_parameters(self, mock_repository, conversation_context):
        """Test clear method with all parameters."""
        mock_repository.clear_mock.return_value = 1

        result = mock_repository.clear(memory_id="test_memory_id", context=conversation_context)

        assert result == 1
        mock_repository.clear_mock.assert_called_once_with("test_memory_id", conversation_context)

    def test_clear_method_returns_zero(self, mock_repository):
        """Test clear method can return zero."""
        mock_repository.clear_mock.return_value = 0

        result = mock_repository.clear()

        assert result == 0
        mock_repository.clear_mock.assert_called_once_with(None, None)
