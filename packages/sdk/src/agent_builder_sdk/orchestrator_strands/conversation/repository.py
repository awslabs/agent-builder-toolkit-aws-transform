# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Repository interface for multi-source conversation management."""

from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import List

from strands.agent import Agent
from strands.types.content import Message

from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType

conversation_source_id: ContextVar[str] = ContextVar("conversation_source_id")
conversation_source_type: ContextVar[MessageSourceType] = ContextVar("conversation_source_type")


class ConversationRepository(ABC):
    """
    Repository interface for managing multi-source conversations.

    Provides storage and retrieval of conversation histories for different
    message sources, with support for user-specific, task-specific, and
    notification messages.
    """

    @abstractmethod
    def add_message_for_agent(self, message: Message, agent: Agent) -> None:
        """
        Store a message in the appropriate conversation context.

        Args:
            message: The message to store
            agent: The agent providing the conversation context
        """
        pass

    @abstractmethod
    def get_conversation_history_for_agent(self, agent: Agent) -> List[Message]:
        """
        Retrieve conversation history for an agent's context.

        Args:
            agent: The agent whose context determines the relevant history

        Returns:
            List of messages relevant to the agent's context
        """
        pass

    @abstractmethod
    def save(self) -> None:
        """Persist conversations to storage."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Load conversations from storage."""
        pass
