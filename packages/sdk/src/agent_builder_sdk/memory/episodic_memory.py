"""
Episodic memory implementation with built-in type identification.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_repository import MemoryRepository
from agent_builder_sdk.memory.memory_types import MemoryTypeBase, MemoryTypeEnum

# Get logger
logger = logging.getLogger(__name__)


class EpisodicMemory(MemoryTypeBase):
    """
    Episodic memory implementation with built-in type identification.

    Stores natural language memories with conversation context.
    """

    def __init__(self, repository: MemoryRepository):
        """
        Initialize episodic memory.

        Args:
            repository: Repository for storing and retrieving memories
        """
        super().__init__()
        self.repository = repository
        logger.info("Initialized episodic memory")

    @property
    def memory_type(self) -> MemoryTypeEnum:
        """Return the memory type."""
        return MemoryTypeEnum.EPISODIC

    def store(
        self,
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a memory.

        Args:
            context: Conversation context
            content: Natural language content to store
            metadata: Optional metadata

        Returns:
            Memory ID if stored successfully, empty string otherwise
        """
        try:
            # Generate memory ID
            memory_id = str(uuid.uuid4())

            # Store in repository
            success = self.repository.store(
                memory_id=memory_id,
                timestamp=datetime.now(),
                context=context,
                content=content,
                metadata=metadata,
            )

            if success:
                return memory_id
            else:
                return ""

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return ""

    def retrieve(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories.

        Args:
            context: Conversation context
            memory_id: Optional memory ID to retrieve a specific memory
            limit: Optional maximum number of memories to retrieve

        Returns:
            List of memories
        """
        try:
            return self.repository.retrieve(
                memory_id=memory_id,
                context=context,
                limit=limit,
            )

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    def clear(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
    ) -> int:
        """
        Clear memories.

        Args:
            context: Conversation context
            memory_id: Optional memory ID to clear a specific memory

        Returns:
            Number of memories cleared
        """
        try:
            return self.repository.clear(
                memory_id=memory_id,
                context=context,
            )

        except Exception as e:
            logger.error(f"Failed to clear memories: {e}")
            return 0

    def format_for_context(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format memories for inclusion in message context.

        Args:
            memories: List of memories to format

        Returns:
            Formatted string for context
        """
        if not memories:
            return ""

        formatted_memories = []
        for memory in memories:
            # Get timestamp and content
            timestamp_str = memory.get("timestamp", "")
            content = memory.get("content", "")

            # Format as timestamp and content
            try:
                # Handle Z timezone indicator for Python 3.10 compatibility
                iso_str = timestamp_str.replace("Z", "+00:00") if timestamp_str else ""
                timestamp = datetime.fromisoformat(iso_str)
                formatted_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                formatted_timestamp = timestamp_str

            memory_str = f"[{formatted_timestamp}] {content}"
            formatted_memories.append(memory_str)

        return "\n".join(formatted_memories)

    def get_context_for_message(
        self,
        message: str,
        memory_context: MemoryContext,
        limit: int = 5,
    ) -> str:
        """
        Get relevant context to append to the incoming message.

        Args:
            message: The user message to get context for
            memory_context: Structured context for memory retrieval
            limit: Maximum number of memories to retrieve

        Returns:
            Context string to prepend to the message
        """
        try:
            # Retrieve recent memories
            memories = self.retrieve(
                context=memory_context.conversation_context,
                limit=limit,
            )

            if not memories:
                return ""

            # Format memories for context
            formatted_context = self.format_for_context(memories)

            if formatted_context:
                return f"Previous conversation context:\n{formatted_context}\n\n"

            return ""

        except Exception as e:
            logger.error(f"Failed to get context for message: {e}")
            return ""
