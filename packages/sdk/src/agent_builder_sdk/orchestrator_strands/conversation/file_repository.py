# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""File-based implementation of the conversation repository."""

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict, cast

from strands.agent import Agent
from strands.types.content import Message

from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    DEFAULT_SOURCE_ID,
    MessageSourceType,
)
from agent_builder_sdk.orchestrator_strands.conversation.message_type import (
    ConversationMessage,
)
from agent_builder_sdk.orchestrator_strands.conversation.repository import (
    ConversationRepository,
    conversation_source_id,
    conversation_source_type,
)
from agent_builder_sdk.utils import (
    reconcile_dangling_tool_uses,
    reconcile_unanswered_user_turns,
)


# Type definitions for serialization
class SerializedConversations(TypedDict):
    conversations: Dict[str, Dict[str, List[Dict[str, Any]]]]
    saved_at: str


logger = logging.getLogger(__name__)


def _interrupt_pending(agent: Agent) -> bool:
    """Whether Strands is holding an interrupt for this agent.

    A toolUse waiting on an interrupt response is not dangling — Strands replays the tool and
    appends the real toolResult on resume — so repairing it would put two results after one
    toolUse and make the resume request invalid.

    Reads Strands-private state because no public accessor exists; if that attribute is renamed
    this reports no interrupt, which repairs as it did before the guard existed.
    """
    return bool(getattr(getattr(agent, "_interrupt_state", None), "activated", False))


def _tracking_id(message: Any) -> Optional[str]:
    """The Strands tracking id of ``message``, or None; a stored message is any JSON value."""
    if not isinstance(message, dict):
        return None
    return message.get("tracking_id") or None


def _first_block_identity(message: Any) -> Optional[int]:
    """The ``id`` of the first content block of ``message``, or None when it has no dict block.

    The load repair completes a tool result answered in part in a copy that holds the stored
    message's own blocks, so this finds the stored message from that copy where no id does.
    """
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return id(content[0])
    return None


# Strands releases that declare the key send only role and content to the model. An older
# release passes every key of the message on, so the key must not be added there.
_STRANDS_OWNS_TRACKING_ID = "tracking_id" in Message.__annotations__


def _ensure_tracking_id(message: Any) -> None:
    """Give ``message`` a tracking id when it has none and the Strands release owns the key.

    With the id, a fold finds the stored message from a copy of it that shares no object
    with it. Strands releases that assign the id themselves keep theirs.
    """
    if _STRANDS_OWNS_TRACKING_ID and isinstance(message, dict) and not message.get("tracking_id"):
        message["tracking_id"] = str(uuid.uuid4())


class FileMultiSourceConversationRepository(ConversationRepository):
    """
    File-based implementation of the multi-source conversation repository.

    Stores conversations in a JSON file on disk. If no storage directory is provided,
    a default directory in the system's temporary directory is used.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize the file-based conversation repository.

        Args:
            storage_dir: Directory to store conversation history. If None, a default
                        directory in the system's temporary directory is used.
        """
        # Use a default directory in the system's temp directory if none is provided
        self.storage_dir = storage_dir or os.path.join(
            tempfile.gettempdir(), "orchestrator", "conversations"
        )

        # Create storage directory if it doesn't exist
        os.makedirs(self.storage_dir, exist_ok=True)

        # Guards the in-memory conversation maps + file writes. Reentrant because
        # add_message_for_agent() calls save() while holding it. Uncontended (and thus
        # ~free) when a single event loop drives the repo (async orchestrator); load-
        # bearing when one repo instance is shared across concurrent streaming agents
        # AND a sync orchestrator runs the buffered turn in a separate thread
        # (asyncio.to_thread), where two threads could otherwise interleave a save().
        self._lock = threading.RLock()

        # Initialize conversation storage
        # Using a structure: {source_type: {source_id: [ConversationMessage]}}
        self.conversations: Dict[str, Dict[str, List[ConversationMessage]]] = {
            MessageSourceType.USER.value: {},
            MessageSourceType.SUBAGENT.value: {},
            MessageSourceType.NOTIFICATION.value: {DEFAULT_SOURCE_ID: []},
        }

        # Load conversation state if available
        self.load()

    def _get_source_info(self, agent: Agent) -> tuple[MessageSourceType, str]:
        """
        Extract source type and ID from agent state.

        Args:
            agent: The agent containing the source information

        Returns:
            Tuple of (source_type, source_id)
        """
        # Get source information from agent state, default to system notification
        try:
            source_type = conversation_source_type.get()
        except LookupError:
            source_type = MessageSourceType.NOTIFICATION

        if source_type == MessageSourceType.NOTIFICATION:
            source_id = DEFAULT_SOURCE_ID
        else:
            try:
                source_id = conversation_source_id.get()
            except LookupError:
                source_id = DEFAULT_SOURCE_ID

        return source_type, source_id

    def add_message_for_agent(self, message: Message, agent: Agent) -> None:
        """
        Add a message to the appropriate conversation based on agent state.

        Args:
            message: The message to add
            agent: The agent whose state determines the message context
        """
        source_type, source_id = self._get_source_info(agent)

        with self._lock:
            # Ensure the source_id exists in the conversations dictionary
            source_type_str = source_type.value
            if source_id not in self.conversations[source_type_str]:
                self.conversations[source_type_str][source_id] = []

            _ensure_tracking_id(message)

            # Convert to our custom message type
            conversation_message = ConversationMessage.from_message(message)

            # Add the message to the appropriate conversation
            self.conversations[source_type_str][source_id].append(conversation_message)

            # Save conversation state
            self.save()

    def get_conversation_history_for_agent(self, agent: Agent) -> List[Message]:
        """
        Get the conversation history relevant to an agent based on its state.

        Args:
            agent: The agent whose state determines which conversations to retrieve

        Returns:
            List of messages relevant to the agent's context
        """
        source_type, source_id = self._get_source_info(agent)

        with self._lock:
            # Build a FRESH list each call. This list is handed to Strands as
            # agent.messages and mutated by the framework OUTSIDE this lock during the
            # invocation, so it must not be an instance shared across agents: when one
            # repository is shared by several agents for the same source (e.g. the
            # shared singleton agent that serves message/send and a per-user streaming
            # agent, both for the same user), aliasing one list would let two concurrent
            # invocations clear/append each other's in-flight history. The durable store
            # (self.conversations) stays serialized by _lock; the returned list is only a
            # per-invocation working copy.
            history: List[Message] = []

            source_type_str = source_type.value
            if source_id in self.conversations[source_type_str]:
                history.extend(
                    msg.to_message() for msg in self.conversations[source_type_str][source_id]
                )

            # Repair before the notification merge: a toolResult must sit in the message
            # immediately after its toolUse, and notifications append past that point.
            repair = not _interrupt_pending(agent)
            if repair:
                history = reconcile_unanswered_user_turns(reconcile_dangling_tool_uses(history))

            # For users, also include notifications
            if source_type == MessageSourceType.USER:
                notifications = [
                    msg.to_message()
                    for msg in self.conversations[MessageSourceType.NOTIFICATION.value][
                        DEFAULT_SOURCE_ID
                    ]
                ]
                # Closed on their own, so an aborted notification turn does not end the history
                # unanswered and a notification reply never counts as the user's missing reply.
                history.extend(
                    reconcile_unanswered_user_turns(notifications) if repair else notifications
                )

            return history

    def fold_history_for_agent(
        self, folded: List[Message], replacement: List[Message], agent: Agent
    ) -> bool:
        """
        Replace the oldest stored messages of the agent's source with ``replacement``.

        A stored message is folded when it is one of the ``folded`` objects, when it has the
        ``tracking_id`` of one, or when its first content block is the first content block of one
        that is not a stored object itself (the copy the load repair makes of a tool result
        answered in part). Stored messages that only share a block object are kept. Messages in
        ``folded`` that the source does not store (notifications in a user's view, placeholders
        the load repair inserted) are ignored. On a Strands release whose ``Message`` has no
        ``tracking_id``, stored messages get no id, so a deep copy of a message is not matched.

        ``replacement`` becomes the start of the stored history, with the timestamp of the oldest
        folded message. Every entry stored ahead of that message is removed with it, so pass in
        ``replacement`` anything older that must stay. Entries behind it that are not folded keep
        their order, which includes turns appended after the view was read.

        The file is rewritten atomically, and a failed write restores the history in memory.
        The NOTIFICATION source is never folded: every user's view shares its history.

        Args:
            folded: The oldest messages of a view from ``get_conversation_history_for_agent``
            replacement: The messages to store in their place; may be empty
            agent: The agent whose state determines the conversation

        Returns:
            True when the replacement is stored. False, with the stored history unchanged, when
            no stored message is folded, the source is NOTIFICATION, or the write failed.
        """
        source_type, source_id = self._get_source_info(agent)
        if source_type == MessageSourceType.NOTIFICATION:
            logger.info("Folded history not stored: the notification history is never folded")
            return False

        identities = {id(message) for message in folded}
        tracking_ids = {_tracking_id(message) for message in folded} - {None}

        with self._lock:
            source_dict = self.conversations[source_type.value]
            stored = source_dict.get(source_id, [])
            notifications = self.conversations[MessageSourceType.NOTIFICATION.value][
                DEFAULT_SOURCE_ID
            ]
            # A stored object stands only for itself: callers may put one block object first in
            # many messages, and its first block would then match stored messages not folded.
            stored_objects = {id(entry.message) for entry in (*stored, *notifications)}
            first_blocks = {
                _first_block_identity(message)
                for message in folded
                if id(message) not in stored_objects
            } - {None}
            oldest: Optional[ConversationMessage] = None
            kept: List[ConversationMessage] = []
            for entry in stored:
                if (
                    id(entry.message) in identities
                    or _first_block_identity(entry.message) in first_blocks
                    or _tracking_id(entry.message) in tracking_ids
                ):
                    if oldest is None:
                        oldest = entry
                elif oldest is not None:
                    kept.append(entry)
            if oldest is None:
                logger.info("Folded history not stored: no folded message is in the store")
                return False

            for message in replacement:
                _ensure_tracking_id(message)
            source_dict[source_id] = [
                *(
                    ConversationMessage(message=message, created_at=oldest.created_at)
                    for message in replacement
                ),
                *kept,
            ]
            try:
                self._save()
            except Exception:
                source_dict[source_id] = stored
                logger.exception("Folded history not stored: the write failed")
                return False
        return True

    def _read_file(self, path: str) -> Dict[str, Any]:
        """Read JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cast(Dict[str, Any], json.load(f))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {path}: {str(e)}")
            # Create a backup of the corrupted file
            backup_path = path + ".corrupted"
            try:
                os.replace(path, backup_path)
                logger.info(f"Backed up corrupted file to {backup_path}")
            except Exception as backup_error:
                logger.error(f"Failed to backup corrupted file: {backup_error}")
            return {}

    def _write_file(self, path: str, data: Dict[str, Any]) -> None:
        """Write JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Use atomic write pattern to prevent corruption if the process is interrupted
        temp_file = path + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Rename is atomic on most file systems
        os.replace(temp_file, path)

    def save(self) -> None:
        """Save the conversations to disk."""
        try:
            self._save()
        except Exception as e:
            logger.error(f"Failed to save conversations: {e}")

    def _save(self) -> None:
        """Write the conversations to disk; raises when they cannot be written."""
        with self._lock:
            # Create a serializable representation of the conversations
            serializable_conversations: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

            for source_type_str, source_dict in self.conversations.items():
                serializable_conversations[source_type_str] = {}

                for source_id, messages in source_dict.items():
                    # Convert each ConversationMessage to a serializable format
                    serializable_conversations[source_type_str][source_id] = [
                        msg.to_dict() for msg in messages
                    ]

            # Save to disk
            file_path = os.path.join(self.storage_dir, "conversations.json")

            # Save with metadata
            self._write_file(
                file_path,
                {
                    "conversations": serializable_conversations,
                    "saved_at": datetime.now().isoformat(),
                },
            )

        logger.info(f"Saved conversations to disk at {file_path}")

    def load(self) -> None:
        """Load the conversations from disk."""
        file_path = os.path.join(self.storage_dir, "conversations.json")
        if not os.path.exists(file_path):
            logger.info(
                f"No conversation file found at {file_path}, starting with empty conversations"
            )
            return

        try:
            # Load from disk
            data = self._read_file(file_path)
            if not data:
                logger.warning(
                    f"Empty or invalid data in {file_path}, starting with empty conversations"
                )
                return

            # Restore conversations
            serialized_conversations = data.get("conversations", {})

            with self._lock:
                # Convert serialized data back to ConversationMessage objects
                for source_type_str, source_dict in serialized_conversations.items():
                    if source_type_str not in self.conversations:
                        self.conversations[source_type_str] = {}

                    for source_id, messages in source_dict.items():
                        entries = [ConversationMessage.from_dict(msg) for msg in messages]
                        for entry in entries:
                            _ensure_tracking_id(entry.message)
                        self.conversations[source_type_str][source_id] = entries

                # Ensure all required source types exist
                for source_type in MessageSourceType:
                    if source_type.value not in self.conversations:
                        self.conversations[source_type.value] = {}

                # Ensure notifications have a default source_id
                if (
                    DEFAULT_SOURCE_ID
                    not in self.conversations[MessageSourceType.NOTIFICATION.value]
                ):
                    self.conversations[MessageSourceType.NOTIFICATION.value][DEFAULT_SOURCE_ID] = []

            # Log when the data was last saved
            saved_at = data.get("saved_at", "unknown time")
            logger.info(f"Loaded conversations from disk: {file_path} (saved at {saved_at})")
        except Exception as e:
            logger.error(f"Failed to load conversations: {e}")
