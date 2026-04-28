"""
Memory type definitions and base classes.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    ConversationContext,
    MemoryContext,
)


class MemoryTypeEnum(Enum):
    """Enum for memory type identifiers."""

    EPISODIC = "episodic"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


class MemoryTypeBase(ABC):
    """Base class for all memory types with built-in type identification."""

    @property
    @abstractmethod
    def memory_type(self) -> MemoryTypeEnum:
        """Return the memory type enum."""
        pass

    @abstractmethod
    def store(
        self,
        context: ConversationContext,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory."""
        pass

    @abstractmethod
    def retrieve(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve memories."""
        pass

    @abstractmethod
    def clear(
        self,
        context: ConversationContext,
        memory_id: Optional[str] = None,
    ) -> int:
        """Clear memories."""
        pass

    @abstractmethod
    def get_context_for_message(
        self,
        message: str,
        memory_context: MemoryContext,
        limit: int = 5,
    ) -> str:
        """Get context for message."""
        pass
