"""Hook provider for managing multi-source conversations in Strands agents."""

import logging
from typing import Any, Optional

from strands.hooks.events import AfterInvocationEvent, BeforeInvocationEvent, MessageAddedEvent
from strands.hooks.registry import HookProvider, HookRegistry

from agent_builder_sdk.orchestrator_strands.conversation.file_repository import (
    FileMultiSourceConversationRepository,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    ConversationRepository,
)

logger = logging.getLogger(__name__)


class ConversationHookProvider(HookProvider):
    """
    Hook provider for managing conversations from different sources.

    Provides conversation history management for different message sources:
    - User messages include user-specific history and notifications
    - Subagent messages include task-specific conversations
    - Notifications are shared across user contexts

    Args:
        repository: Repository for storing and retrieving conversations.
                   If None, a FileConversationRepository with default settings is used.
        storage_dir: Directory to store conversation history (only used if repository is None).
                    If None, conversations are only kept in memory.
    """

    def __init__(
        self, repository: Optional[ConversationRepository] = None, storage_dir: Optional[str] = None
    ):
        """Initialize the conversation hook provider."""
        # Initialize the repository
        self.repository = repository or FileMultiSourceConversationRepository(
            storage_dir=storage_dir
        )

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register hooks for conversation management."""

        # Before agent invocation, set the appropriate conversation history
        registry.add_callback(BeforeInvocationEvent, self._before_invocation)

        # After a message is added, store it with source information
        registry.add_callback(MessageAddedEvent, self._on_message_added)

        # After agent invocation, save the conversation state
        registry.add_callback(AfterInvocationEvent, self._after_invocation)

    def _before_invocation(self, event: BeforeInvocationEvent) -> None:
        """
        Set the conversation history before agent invocation.

        Args:
            event: The BeforeInvocationEvent containing the agent and invocation state
        """
        # Get conversation history from repository based on agent state
        history = self.repository.get_conversation_history_for_agent(event.agent)

        # Update the agent's conversation with the relevant history
        event.agent.messages = history

        logger.info(
            f"Set conversation history for agent {event.agent.agent_id} with history length: {len(history)}"
        )

    def _on_message_added(self, event: MessageAddedEvent) -> None:
        """
        Store a message when it's added to the agent.

        Args:
            event: The MessageAddedEvent containing the message and agent
        """
        # Let the repository handle the message storage based on agent state
        self.repository.add_message_for_agent(event.message, event.agent)

    def _after_invocation(self, event: AfterInvocationEvent) -> None:
        """
        Save the conversation state after agent invocation.

        Args:
            event: The AfterInvocationEvent containing the agent
        """
        # Save conversation state
        self.repository.save()
