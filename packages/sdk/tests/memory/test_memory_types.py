# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for memory_types module.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_types import MemoryTypeBase, MemoryTypeEnum


class TestMemoryTypeEnum:
    """Test cases for MemoryTypeEnum."""

    def test_enum_values(self):
        """Test that enum has expected values."""
        assert MemoryTypeEnum.EPISODIC.value == "episodic"
        assert str(MemoryTypeEnum.EPISODIC) == "episodic"

    def test_enum_string_conversion(self):
        """Test string conversion of enum."""
        assert str(MemoryTypeEnum.EPISODIC) == "episodic"


class MockMemoryType(MemoryTypeBase):
    """Mock implementation of MemoryTypeBase for testing."""

    def __init__(self, memory_type: MemoryTypeEnum):
        self._memory_type = memory_type
        self.store_mock = Mock()
        self.retrieve_mock = Mock()
        self.clear_mock = Mock()
        self.get_context_mock = Mock()

    @property
    def memory_type(self) -> MemoryTypeEnum:
        return self._memory_type

    def store(
        self,
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.store_mock(context, content, metadata)

    def retrieve(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.retrieve_mock(context, memory_id, limit)

    def clear(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
    ) -> int:
        return self.clear_mock(context, memory_id)

    def get_context_for_message(
        self,
        message: str,
        memory_context: MemoryContext,
        limit: int = 5,
    ) -> str:
        return self.get_context_mock(message, memory_context, limit)


class TestMemoryTypeBase:
    """Test cases for MemoryTypeBase abstract class."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock memory type for testing."""
        return MockMemoryType(MemoryTypeEnum.EPISODIC)

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

    def test_memory_type_property(self, mock_memory):
        """Test that memory_type property returns correct enum."""
        assert mock_memory.memory_type == MemoryTypeEnum.EPISODIC

    def test_store_method_signature(self, mock_memory, conversation_context):
        """Test store method can be called with expected parameters."""
        mock_memory.store_mock.return_value = "test_memory_id"

        result = mock_memory.store(
            context=conversation_context, content="test content", metadata={"key": "value"}
        )

        assert result == "test_memory_id"
        mock_memory.store_mock.assert_called_once_with(
            conversation_context, "test content", {"key": "value"}
        )

    def test_store_method_without_metadata(self, mock_memory, conversation_context):
        """Test store method works without metadata."""
        mock_memory.store_mock.return_value = "test_memory_id"

        result = mock_memory.store(context=conversation_context, content="test content")

        assert result == "test_memory_id"
        mock_memory.store_mock.assert_called_once_with(conversation_context, "test content", None)

    def test_retrieve_method_signature(self, mock_memory, conversation_context):
        """Test retrieve method can be called with expected parameters."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_memory.retrieve_mock.return_value = expected_memories

        result = mock_memory.retrieve(
            context=conversation_context, memory_id="test_memory_id", limit=10
        )

        assert result == expected_memories
        mock_memory.retrieve_mock.assert_called_once_with(
            conversation_context, "test_memory_id", 10
        )

    def test_retrieve_method_with_defaults(self, mock_memory, conversation_context):
        """Test retrieve method works with default parameters."""
        expected_memories = [{"memory_id": "test", "content": "test content"}]
        mock_memory.retrieve_mock.return_value = expected_memories

        result = mock_memory.retrieve(context=conversation_context)

        assert result == expected_memories
        mock_memory.retrieve_mock.assert_called_once_with(conversation_context, None, None)

    def test_clear_method_signature(self, mock_memory, conversation_context):
        """Test clear method can be called with expected parameters."""
        mock_memory.clear_mock.return_value = 5

        result = mock_memory.clear(context=conversation_context, memory_id="test_memory_id")

        assert result == 5
        mock_memory.clear_mock.assert_called_once_with(conversation_context, "test_memory_id")

    def test_clear_method_without_memory_id(self, mock_memory, conversation_context):
        """Test clear method works without memory_id."""
        mock_memory.clear_mock.return_value = 3

        result = mock_memory.clear(context=conversation_context)

        assert result == 3
        mock_memory.clear_mock.assert_called_once_with(conversation_context, None)

    def test_get_context_for_message_signature(self, mock_memory, memory_context):
        """Test get_context_for_message method can be called with expected parameters."""
        expected_context = "Previous context"
        mock_memory.get_context_mock.return_value = expected_context

        result = mock_memory.get_context_for_message(
            message="test message", memory_context=memory_context, limit=10
        )

        assert result == expected_context
        mock_memory.get_context_mock.assert_called_once_with("test message", memory_context, 10)

    def test_get_context_for_message_with_default_limit(self, mock_memory, memory_context):
        """Test get_context_for_message method works with default limit."""
        expected_context = "Previous context"
        mock_memory.get_context_mock.return_value = expected_context

        result = mock_memory.get_context_for_message(
            message="test message", memory_context=memory_context
        )

        assert result == expected_context
        mock_memory.get_context_mock.assert_called_once_with("test message", memory_context, 5)
