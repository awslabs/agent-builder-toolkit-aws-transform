# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the FileMultiSourceConversationRepository class."""

import os
import tempfile
from unittest.mock import Mock

import pytest
from strands.agent import Agent
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    DEFAULT_SOURCE_ID,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.conversation.message_type import (
    ConversationMessage,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    conversation_source_id,
    conversation_source_type,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def repository(temp_dir):
    """Create a FileMultiSourceConversationRepository instance."""
    return FileMultiSourceConversationRepository(storage_dir=temp_dir)


@pytest.fixture
def mock_agent():
    """Create a mock Agent instance."""
    agent = Mock(spec=Agent)
    agent.state = {}
    return agent


def test_initialization_with_storage_dir(temp_dir):
    """Test repository initialization with storage directory."""
    repo = FileMultiSourceConversationRepository(storage_dir=temp_dir)
    assert repo.storage_dir == temp_dir
    assert os.path.exists(temp_dir)


def test_initialization_without_storage_dir():
    """Test repository initialization without storage directory."""
    repo = FileMultiSourceConversationRepository()
    expected_dir = os.path.join(tempfile.gettempdir(), "orchestrator", "conversations")
    assert repo.storage_dir == expected_dir
    assert os.path.exists(expected_dir)


def test_add_message_for_agent_user(repository, mock_agent):
    """Test adding a user message."""
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")

    message = Message(role="user", content=[ContentBlock(text="Test message")])
    repository.add_message_for_agent(message, mock_agent)

    # Verify message was stored
    assert len(repository.conversations[MessageSourceType.USER.value]["test-user"]) == 1
    stored_message = repository.conversations[MessageSourceType.USER.value]["test-user"][0]
    assert isinstance(stored_message, ConversationMessage)
    assert stored_message.to_message()["role"] == "user"
    assert stored_message.to_message()["content"][0]["text"] == "Test message"


def test_add_message_for_agent_notification(repository, mock_agent):
    """Test adding a notification message."""
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set("any-id")  # Should use DEFAULT_SOURCE_ID

    message = Message(role="assistant", content=[ContentBlock(text="Test notification")])
    repository.add_message_for_agent(message, mock_agent)

    # Verify message was stored with default source ID
    notifications = repository.conversations[MessageSourceType.NOTIFICATION.value][
        DEFAULT_SOURCE_ID
    ]
    assert len(notifications) == 1
    assert notifications[0].to_message()["content"][0]["text"] == "Test notification"


def test_get_conversation_history_for_agent_user(repository, mock_agent):
    """Test retrieving conversation history for a user."""
    # Add a user message
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    user_message = Message(role="user", content=[ContentBlock(text="User message")])
    repository.add_message_for_agent(user_message, mock_agent)

    # Add a notification
    conversation_source_type.set(MessageSourceType.NOTIFICATION)
    conversation_source_id.set(DEFAULT_SOURCE_ID)
    notification = Message(role="assistant", content=[ContentBlock(text="Notification")])
    repository.add_message_for_agent(notification, mock_agent)

    # Get history for user
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    history = repository.get_conversation_history_for_agent(mock_agent)

    # Should include both user message and notification
    assert len(history) == 2
    assert any(msg["content"][0]["text"] == "User message" for msg in history)
    assert any(msg["content"][0]["text"] == "Notification" for msg in history)


def test_save_and_load(repository, temp_dir, mock_agent):
    """Test saving and loading conversations."""
    # Add some messages
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("test-user")
    message = Message(role="user", content=[ContentBlock(text="Test message")])
    repository.add_message_for_agent(message, mock_agent)

    # Create new repository instance to load saved data
    new_repository = FileMultiSourceConversationRepository(storage_dir=temp_dir)

    # Verify messages were loaded
    assert len(new_repository.conversations[MessageSourceType.USER.value]["test-user"]) == 1
    loaded_message = new_repository.conversations[MessageSourceType.USER.value]["test-user"][0]
    assert loaded_message.to_message()["content"][0]["text"] == "Test message"


def test_corrupted_file_handling(temp_dir):
    """Test handling of corrupted conversation file."""
    # Create corrupted JSON file
    file_path = os.path.join(temp_dir, "conversations.json")
    with open(file_path, "w") as f:
        f.write("{ invalid json")

    # Repository should handle corrupted file gracefully
    repository = FileMultiSourceConversationRepository(storage_dir=temp_dir)

    # Verify backup was created
    assert os.path.exists(file_path + ".corrupted")

    # Verify empty conversations were initialized
    assert MessageSourceType.USER.value in repository.conversations
    assert MessageSourceType.NOTIFICATION.value in repository.conversations
    assert DEFAULT_SOURCE_ID in repository.conversations[MessageSourceType.NOTIFICATION.value]
