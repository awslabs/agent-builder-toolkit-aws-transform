# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Repository interface for memory storage.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext

# Get logger
logger = logging.getLogger(__name__)


class MemoryRepository(ABC):
    """
    Interface for memory storage repositories.

    This defines the contract for storing and retrieving memory items.
    """

    @abstractmethod
    def store(
        self,
        memory_id: str,
        timestamp: datetime,
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store a memory.

        Args:
            memory_id: Unique identifier for the memory
            timestamp: Timestamp for the memory
            context: Conversation context
            content: Natural language content
            metadata: Optional metadata

        Returns:
            True if stored successfully, False otherwise
        """
        pass

    @abstractmethod
    def retrieve(
        self,
        memory_id: Optional[str] = None,
        context: Optional[ConversationContext] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories.

        Args:
            memory_id: Optional memory ID to retrieve a specific memory
            context: Optional conversation context to filter by
            limit: Optional maximum number of memories to retrieve

        Returns:
            List of memories
        """
        pass

    @abstractmethod
    def clear(
        self,
        memory_id: Optional[str] = None,
        context: Optional[ConversationContext] = None,
    ) -> int:
        """
        Clear memories.

        Args:
            memory_id: Optional memory ID to clear a specific memory
            context: Optional conversation context to filter by

        Returns:
            Number of memories cleared
        """
        pass
