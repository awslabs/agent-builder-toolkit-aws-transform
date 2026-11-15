# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Repository interface for multi-source conversation management."""

from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import List, Optional

from strands.agent import Agent
from strands.types.content import Message

from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType

conversation_source_id: ContextVar[str] = ContextVar("conversation_source_id")
conversation_source_type: ContextVar[MessageSourceType] = ContextVar("conversation_source_type")
# time.monotonic() value at which the reply window of the queued user turn being run ends. Set by
# the queue worker; None when nobody waits for the turn's reply.
turn_deadline: ContextVar[Optional[float]] = ContextVar("turn_deadline", default=None)


@dataclass
class TurnErrorNote:
    """A message for the user that replaces the error a user turn ends with.

    The code that delivers the turn's reply creates an empty note; a hook that gives up on the
    turn fills it in. The note is mutable because hooks can run in a copy of the caller's context,
    where setting a context variable would not reach the caller.
    """

    text: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    exception: Optional[BaseException] = None

    def explains(self, raised: BaseException) -> bool:
        """Whether the note was left for ``raised``, as raised or as the cause of the exception
        Strands wraps a model error in after the first event-loop cycle."""
        if self.exception is None:
            return False
        return raised is self.exception or raised.__cause__ is self.exception


# The note of the queued user turn being run. Set by the queue worker; None when no reply is
# delivered for the turn.
turn_error_note: ContextVar[Optional[TurnErrorNote]] = ContextVar("turn_error_note", default=None)


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
