# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ConversationHookProvider class."""

from unittest.mock import Mock, patch

import pytest
from strands.agent import Agent
from strands.hooks.events import AfterInvocationEvent, BeforeInvocationEvent, MessageAddedEvent
from strands.hooks.registry import HookRegistry
from strands.models import Model
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


class _ScriptedModel(Model):
    """A Strands model that plays scripted turns and records the messages each call received."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        import copy

        self.seen.append(copy.deepcopy(messages))
        for event in self.turns.pop(0):
            yield event


def _tool_use_turn(name):
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": name}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]


def _text_turn(text):
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]


def test_force_stopped_turn_is_stored_with_its_answer(tmp_path):
    """A terminating tool ends the turn on its toolResult; the answer the user got is stored as the
    reply, so the next turn sees it instead of an "interrupted" placeholder."""
    from strands import tool
    from strands.types.tools import ToolContext

    from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
    from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
        FileMultiSourceConversationRepository,
    )
    from agent_builder_sdk.orchestrator_strands.conversation.repository import (
        conversation_source_id,
        conversation_source_type,
    )
    from agent_builder_sdk.utils import INTERRUPTED_TURN_TEXT

    @tool(context=True)
    def finish(tool_context: ToolContext) -> str:
        """End the turn with a fixed answer."""
        request_state = tool_context.invocation_state["request_state"]
        request_state["force_stop_response"] = "FORCED ANSWER"
        request_state["stop_event_loop"] = True
        return "done"

    model = _ScriptedModel([_tool_use_turn("finish"), _text_turn("ok")])
    repository = FileMultiSourceConversationRepository(storage_dir=str(tmp_path))
    agent = Agent(
        model=model,
        tools=[finish],
        hooks=[ConversationHookProvider(repository=repository)],
        callback_handler=None,
    )
    conversation_source_type.set(MessageSourceType.USER)
    conversation_source_id.set("u1")

    agent("first")
    agent("second")

    second_input = model.seen[-1]
    assert [m["role"] for m in second_input] == ["user", "assistant", "user", "assistant", "user"]
    assert second_input[3]["content"] == [{"text": "FORCED ANSWER"}]
    assert INTERRUPTED_TURN_TEXT not in str(second_input)
