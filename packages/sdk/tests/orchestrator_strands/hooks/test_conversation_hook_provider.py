# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ConversationHookProvider class."""

from unittest.mock import Mock, patch

import pytest
from strands.agent import Agent
from strands.hooks.events import AfterInvocationEvent, BeforeInvocationEvent, MessageAddedEvent
from strands.hooks.registry import HookRegistry
from strands.types.content import ContentBlock, Message

from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    ConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider import (
    ConversationHookProvider,
)


@pytest.fixture
def mock_repository():
    """Create a mock conversation repository."""
    return Mock(spec=ConversationRepository)


@pytest.fixture
def hook_provider(mock_repository):
    """Create a ConversationHookProvider instance."""
    return ConversationHookProvider(repository=mock_repository)


@pytest.fixture
def mock_registry():
    """Create a mock hook registry."""
    return Mock(spec=HookRegistry)


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = Mock(spec=Agent)
    agent.agent_id = "test-agent-id"  # Add agent_id attribute
    return agent


def test_initialization_with_repository(mock_repository):
    """Test initialization with provided repository."""
    provider = ConversationHookProvider(repository=mock_repository)
    assert provider.repository == mock_repository


def test_initialization_without_repository():
    """Test initialization without repository."""
    with patch(
        "agent_builder_sdk.orchestrator_strands.hooks.conversation_hook_provider.FileMultiSourceConversationRepository"
    ) as mock_file_repo:
        provider = ConversationHookProvider()
        mock_file_repo.assert_called_once_with(storage_dir=None)
        assert provider.repository == mock_file_repo.return_value


def test_register_hooks(hook_provider, mock_registry):
    """Test hook registration."""
    hook_provider.register_hooks(mock_registry)

    # Verify all hooks were registered
    assert mock_registry.add_callback.call_count == 3

    # Get the registered event types
    registered_events = [call.args[0] for call in mock_registry.add_callback.call_args_list]

    # Verify correct events were registered
    assert BeforeInvocationEvent in registered_events
    assert MessageAddedEvent in registered_events
    assert AfterInvocationEvent in registered_events


def test_before_invocation_hook(hook_provider, mock_agent):
    """Test before invocation hook."""
    # Setup mock repository response
    history = [Message(role="user", content=[ContentBlock(text="Test message")])]
    hook_provider.repository.get_conversation_history_for_agent.return_value = history

    # Create event
    event = BeforeInvocationEvent(agent=mock_agent)

    # Call hook
    hook_provider._before_invocation(event)

    # Verify repository was queried
    hook_provider.repository.get_conversation_history_for_agent.assert_called_once_with(mock_agent)

    # Verify agent's messages were updated
    assert mock_agent.messages == history


def test_message_added_hook(hook_provider, mock_agent):
    """Test message added hook."""
    # Create message and event
    message = Message(role="user", content=[ContentBlock(text="Test message")])
    event = MessageAddedEvent(message=message, agent=mock_agent)

    # Call hook
    hook_provider._on_message_added(event)

    # Verify message was stored
    hook_provider.repository.add_message_for_agent.assert_called_once_with(message, mock_agent)


def test_after_invocation_hook(hook_provider, mock_agent):
    """Test after invocation hook."""
    # Create event
    event = AfterInvocationEvent(agent=mock_agent)

    # Call hook
    hook_provider._after_invocation(event)

    # Verify conversation state was saved
    hook_provider.repository.save.assert_called_once()
