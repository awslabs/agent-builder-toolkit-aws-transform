"""File-based implementation of the conversation repository."""

import json
import logging
import os
import tempfile
from collections import defaultdict
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


# Type definitions for serialization
class SerializedConversations(TypedDict):
    conversations: Dict[str, Dict[str, List[Dict[str, Any]]]]
    saved_at: str


logger = logging.getLogger(__name__)


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

        # Initialize conversation storage
        # Using a structure: {source_type: {source_id: [ConversationMessage]}}
        self.conversations: Dict[str, Dict[str, List[ConversationMessage]]] = {
            MessageSourceType.USER.value: {},
            MessageSourceType.SUBAGENT.value: {},
            MessageSourceType.NOTIFICATION.value: {DEFAULT_SOURCE_ID: []},
        }

        # List returned by get_conversation_history_for_agent
        # Store in this dict to ensure the same source always gets the same list instance
        # Using a structure: {source_type: {source_id: [Message]}}
        self._messages: dict[str, dict[str, list[Message]]] = {
            MessageSourceType.USER.value: defaultdict(list),
            MessageSourceType.SUBAGENT.value: defaultdict(list),
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

        # Ensure the source_id exists in the conversations dictionary
        source_type_str = source_type.value
        if source_id not in self.conversations[source_type_str]:
            self.conversations[source_type_str][source_id] = []

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

        # Ensure the same source uses the same list instance
        history = self._messages[source_type.value][source_id]
        # Clear the list to avoid duplicates after the persisted conversation is appended
        history.clear()

        # Get the source-specific conversation
        source_type_str = source_type.value
        if source_id in self.conversations[source_type_str]:
            # Convert ConversationMessage objects to Strands Message objects
            source_messages = [
                msg.to_message() for msg in self.conversations[source_type_str][source_id]
            ]
            history.extend(source_messages)

        # For users, also include notifications
        if source_type == MessageSourceType.USER:
            # Convert ConversationMessage objects to Strands Message objects
            notifications = [
                msg.to_message()
                for msg in self.conversations[MessageSourceType.NOTIFICATION.value][
                    DEFAULT_SOURCE_ID
                ]
            ]
            history.extend(notifications)

        return history

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
        except Exception as e:
            logger.error(f"Failed to save conversations: {e}")

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

            # Convert serialized data back to ConversationMessage objects
            for source_type_str, source_dict in serialized_conversations.items():
                if source_type_str not in self.conversations:
                    self.conversations[source_type_str] = {}

                for source_id, messages in source_dict.items():
                    self.conversations[source_type_str][source_id] = [
                        ConversationMessage.from_dict(msg) for msg in messages
                    ]

            # Ensure all required source types exist
            for source_type in MessageSourceType:
                if source_type.value not in self.conversations:
                    self.conversations[source_type.value] = {}

            # Ensure notifications have a default source_id
            if DEFAULT_SOURCE_ID not in self.conversations[MessageSourceType.NOTIFICATION.value]:
                self.conversations[MessageSourceType.NOTIFICATION.value][DEFAULT_SOURCE_ID] = []

            # Log when the data was last saved
            saved_at = data.get("saved_at", "unknown time")
            logger.info(f"Loaded conversations from disk: {file_path} (saved at {saved_at})")
        except Exception as e:
            logger.error(f"Failed to load conversations: {e}")
