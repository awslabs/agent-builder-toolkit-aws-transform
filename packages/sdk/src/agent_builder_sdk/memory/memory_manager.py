# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Memory Manager for orchestrator agents.

This module provides the implementation for memory management in orchestrator agents.
Memory managers are used to store and retrieve memories, and inject relevant context into incoming messages.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)
from agent_builder_sdk.memory.memory_types import MemoryTypeBase, MemoryTypeEnum

# Get logger
logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Memory manager for orchestrator agents.

    Provides context injection for messages and manages different types of memory.
    """

    def __init__(self, memories: Optional[List[MemoryTypeBase]] = None):
        """
        Initialize memory manager.

        Args:
            memories: List of memory type instances (they self-identify their type)
        """
        self.memories: Dict[MemoryTypeEnum, MemoryTypeBase] = {}

        if memories:
            for memory in memories:
                self.memories[memory.memory_type] = memory

        memory_type_names = [memory_type.value for memory_type in self.memories.keys()]
        logger.info(f"Initialized memory manager with memory types: {memory_type_names}")

    def get_context_for_message(
        self, message: str, memory_context: MemoryContext, limit: int = 5
    ) -> str:
        """
        Get relevant context to append to the incoming message.

        This is the primary method that the orchestrator uses to enhance messages
        with memory context.

        Args:
            message: The user message to get context for
            memory_context: Structured context for memory retrieval
            limit: Maximum number of context items to retrieve

        Returns:
            Context string to prepend to the message, or empty string if no context
        """
        try:
            context_parts = []

            # Get context from each memory type
            for memory_type, memory in self.memories.items():
                memory_context_str = memory.get_context_for_message(
                    message=message,
                    memory_context=memory_context,
                    limit=limit,
                )

                if memory_context_str:
                    context_parts.append(memory_context_str)

            # Combine context parts
            if context_parts:
                return "\n".join(context_parts)

            return ""

        except Exception as e:
            logger.error(f"Failed to get context for message: {e}")
            return ""

    def store_memory(
        self,
        memory_type: Union[MemoryTypeEnum, str],
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a memory.

        Args:
            memory_type: Type of memory to store (enum or string)
            context: Conversation context for the memory
            content: Natural language content to store
            metadata: Optional metadata for the memory

        Returns:
            Memory ID if stored successfully, empty string otherwise
        """
        try:
            # Convert string to enum if needed
            if isinstance(memory_type, str):
                try:
                    memory_type = MemoryTypeEnum(memory_type)
                except ValueError:
                    logger.warning(f"Unknown memory type string: {memory_type}")
                    return ""

            if memory_type not in self.memories:
                logger.warning(f"Memory type not configured: {memory_type.value}")
                return ""

            return self.memories[memory_type].store(
                context=context,
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return ""

    def retrieve_memories(
        self,
        memory_type: Union[MemoryTypeEnum, str],
        context: ConversationContext,
        memory_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories.

        Args:
            memory_type: Type of memory to retrieve (enum or string)
            context: Conversation context for the memory
            memory_id: Optional memory ID to retrieve a specific memory
            limit: Optional maximum number of items to retrieve

        Returns:
            List of memories matching the criteria
        """
        try:
            # Convert string to enum if needed
            if isinstance(memory_type, str):
                try:
                    memory_type = MemoryTypeEnum(memory_type)
                except ValueError:
                    logger.warning(f"Unknown memory type string: {memory_type}")
                    return []

            if memory_type not in self.memories:
                logger.warning(f"Memory type not configured: {memory_type.value}")
                return []

            return self.memories[memory_type].retrieve(
                context=context,
                memory_id=memory_id,
                limit=limit,
            )

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    def clear_memory(
        self,
        memory_type: Optional[Union[MemoryTypeEnum, str]] = None,
        context: Optional[ConversationContext] = None,
    ) -> int:
        """
        Clear memory for a given context.

        Args:
            memory_type: Optional type of memory to clear (enum or string)
            context: Optional conversation context to clear memory for

        Returns:
            Number of memory items cleared
        """
        try:
            total_cleared = 0

            # If memory type specified, clear only that type
            if memory_type:
                # Convert string to enum if needed
                if isinstance(memory_type, str):
                    try:
                        memory_type = MemoryTypeEnum(memory_type)
                    except ValueError:
                        logger.warning(f"Unknown memory type string: {memory_type}")
                        return 0

                if memory_type not in self.memories:
                    logger.warning(f"Memory type not configured: {memory_type.value}")
                    return 0

                # Only call clear if context is provided (required by interface)
                if context is not None:
                    return self.memories[memory_type].clear(context=context)
                else:
                    logger.warning("Context is required for clearing specific memory type")
                    return 0

            # Otherwise, clear all memory types
            if context is not None:
                for memory_type, memory in self.memories.items():
                    cleared = memory.clear(context=context)
                    total_cleared += cleared
            else:
                logger.warning("Context is required for clearing memory")
                return 0

            return total_cleared

        except Exception as e:
            logger.error(f"Failed to clear memory: {e}")
            return 0
