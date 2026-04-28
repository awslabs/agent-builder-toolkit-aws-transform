import json
import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext
from agent_builder_sdk.memory.memory_repository import MemoryRepository

# Get logger
logger = logging.getLogger(__name__)


class FileSystemRepository(MemoryRepository):
    """
    File system repository for memory storage.

    Stores memories in JSON files with daily partitioning.
    """

    def __init__(self, storage_path: str):
        """
        Initialize file system repository.

        Args:
            storage_path: Path to the storage directory
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # File lock for thread safety
        self._lock = threading.Lock()

        # In-memory index for faster lookups (memory_id -> date)
        self._memory_index: Dict[str, date] = {}
        self._load_index()

        logger.info(f"Initialized file system repository at {storage_path}")

    def _load_index(self):
        """Load memory index from existing partition files."""
        try:
            self._memory_index = {}

            # Scan all partition files to build index
            for partition_file in self.storage_path.glob("memories_*.json"):
                try:
                    date_str = partition_file.stem.replace("memories_", "")
                    partition_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                    with open(partition_file, "r") as f:
                        partition_data = json.load(f)

                    memories = partition_data.get("memories", [])
                    for memory in memories:
                        memory_id = memory.get("memory_id")
                        if memory_id:
                            self._memory_index[memory_id] = partition_date

                except Exception as e:
                    logger.warning(f"Failed to load partition {partition_file}: {e}")

            logger.debug(f"Loaded memory index with {len(self._memory_index)} memories")

        except Exception as e:
            logger.error(f"Failed to load memory index: {e}")
            self._memory_index = {}

    def _get_partition_file(self, memory_date: date) -> Path:
        """Get the partition file path for a given date."""
        return self.storage_path / f"memories_{memory_date.strftime('%Y-%m-%d')}.json"

    def _load_partition(self, partition_file: Path) -> Dict[str, Any]:
        """Load a partition file, creating it if it doesn't exist."""
        if partition_file.exists():
            try:
                with open(partition_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load partition {partition_file}: {e}")

        # Return empty partition structure
        date_str = partition_file.stem.replace("memories_", "")
        return {
            "date": date_str,
            "memories": [],
            "metadata": {
                "created": datetime.now().isoformat(),
                "memory_count": 0,
            },
        }

    def _save_partition(self, partition_file: Path, partition_data: Dict[str, Any]) -> bool:
        """Save a partition file."""
        try:
            # Update metadata
            partition_data["metadata"]["last_updated"] = datetime.now().isoformat()
            partition_data["metadata"]["memory_count"] = len(partition_data.get("memories", []))

            with open(partition_file, "w") as f:
                json.dump(partition_data, f, indent=2)
            return True

        except Exception as e:
            logger.error(f"Failed to save partition {partition_file}: {e}")
            return False

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
        try:
            # Create memory
            memory = {
                "memory_id": memory_id,
                "timestamp": timestamp.isoformat(),
                "context": {
                    "user_id": context.user_id,
                    "conversation_id": context.conversation_id,
                    "agent_instance_id": context.agent_instance_id,
                },
                "content": content,
                "metadata": metadata or {},
            }

            # Get partition file
            memory_date = timestamp.date()
            partition_file = self._get_partition_file(memory_date)

            with self._lock:
                # Load partition
                partition_data = self._load_partition(partition_file)

                # Check if memory already exists and remove it
                memories = partition_data.get("memories", [])
                memories = [m for m in memories if m.get("memory_id") != memory_id]

                # Add memory
                memories.append(memory)
                partition_data["memories"] = memories

                # Save partition
                if self._save_partition(partition_file, partition_data):
                    # Update index
                    self._memory_index[memory_id] = memory_date
                    logger.debug(f"Stored memory {memory_id} in partition {memory_date}")
                    return True
                else:
                    return False

        except Exception as e:
            logger.error(f"Failed to store memory {memory_id}: {e}")
            return False

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
        try:
            # If specific memory ID requested, use index for fast lookup
            if memory_id:
                return self._retrieve_by_id(memory_id)

            # Otherwise, retrieve memories by context
            return self._retrieve_by_context(context, limit)

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    def _retrieve_by_id(self, memory_id: str) -> List[Dict[str, Any]]:
        """Retrieve a specific memory by ID."""
        try:
            # Check index
            if memory_id not in self._memory_index:
                return []

            memory_date = self._memory_index[memory_id]
            partition_file = self._get_partition_file(memory_date)

            if not partition_file.exists():
                # Index is stale, remove entry
                self._memory_index.pop(memory_id, None)
                return []

            partition_data = self._load_partition(partition_file)
            memories = partition_data.get("memories", [])

            # Find the specific memory
            for memory in memories:
                if memory.get("memory_id") == memory_id:
                    return [memory]

            # Memory not found, index is stale
            self._memory_index.pop(memory_id, None)
            return []

        except Exception as e:
            logger.error(f"Failed to retrieve memory {memory_id}: {e}")
            return []

    def _retrieve_by_context(
        self,
        context: Optional[ConversationContext],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve memories by context."""
        memories = []

        try:
            with self._lock:
                # Get all partition files and sort by date (newest first)
                partition_files = list(self.storage_path.glob("memories_*.json"))
                partition_files.sort(key=lambda f: f.stem.replace("memories_", ""), reverse=True)

                # Process each partition
                for partition_file in partition_files:
                    try:
                        partition_data = self._load_partition(partition_file)
                        partition_memories = partition_data.get("memories", [])

                        # Sort memories by timestamp (newest first)
                        partition_memories.sort(
                            key=lambda m: m.get("timestamp", ""),
                            reverse=True,
                        )

                        # Filter by context if provided
                        if context:
                            filtered_memories = []
                            for memory in partition_memories:
                                memory_context = memory.get("context", {})
                                if self._matches_context(memory_context, context):
                                    filtered_memories.append(memory)
                            partition_memories = filtered_memories

                        # Add memories to result
                        memories.extend(partition_memories)

                        # Apply limit
                        if limit and len(memories) >= limit:
                            memories = memories[:limit]
                            break

                    except Exception as e:
                        logger.error(f"Failed to process partition {partition_file}: {e}")

        except Exception as e:
            logger.error(f"Failed to retrieve memories by context: {e}")

        return memories

    def _matches_context(
        self, memory_context: Dict[str, Any], context: ConversationContext
    ) -> bool:
        """Check if a memory context matches a conversation context."""
        # Match user ID if provided
        if context.user_id and memory_context.get("user_id") != context.user_id:
            return False

        # Match conversation ID if provided
        if (
            context.conversation_id
            and memory_context.get("conversation_id") != context.conversation_id
        ):
            return False

        # Match agent instance ID if provided
        if (
            context.agent_instance_id
            and memory_context.get("agent_instance_id") != context.agent_instance_id
        ):
            return False

        return True

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
        try:
            if memory_id:
                # Clear specific memory
                return self._clear_by_id(memory_id)
            elif context:
                # Clear memories by context
                return self._clear_by_context(context)
            else:
                # Clear all memories
                return self._clear_all()

        except Exception as e:
            logger.error(f"Failed to clear memories: {e}")
            return 0

    def _clear_by_id(self, memory_id: str) -> int:
        """Clear a specific memory by ID."""
        try:
            # Check index
            if memory_id not in self._memory_index:
                return 0

            memory_date = self._memory_index[memory_id]
            partition_file = self._get_partition_file(memory_date)

            if not partition_file.exists():
                # Index is stale, remove entry
                self._memory_index.pop(memory_id, None)
                return 0

            with self._lock:
                # Load partition
                partition_data = self._load_partition(partition_file)
                memories = partition_data.get("memories", [])

                # Remove memory
                original_count = len(memories)
                memories = [m for m in memories if m.get("memory_id") != memory_id]

                if len(memories) == original_count:
                    # Memory not found
                    self._memory_index.pop(memory_id, None)
                    return 0

                # Update partition
                partition_data["memories"] = memories

                if len(memories) == 0:
                    # Remove empty partition file
                    os.unlink(partition_file)
                else:
                    # Save updated partition
                    self._save_partition(partition_file, partition_data)

                # Update index
                self._memory_index.pop(memory_id, None)
                return 1

        except Exception as e:
            logger.error(f"Failed to clear memory {memory_id}: {e}")
            return 0

    def _clear_by_context(self, context: ConversationContext) -> int:
        """Clear memories by context."""
        cleared_count = 0

        try:
            with self._lock:
                # Get all partition files
                partition_files = list(self.storage_path.glob("memories_*.json"))

                # Process each partition
                for partition_file in partition_files:
                    try:
                        partition_data = self._load_partition(partition_file)
                        memories = partition_data.get("memories", [])

                        # Filter memories to keep
                        original_count = len(memories)
                        memories_to_keep = []

                        for memory in memories:
                            memory_context = memory.get("context", {})

                            # Keep memory if it doesn't match the context
                            if not self._matches_context(memory_context, context):
                                memories_to_keep.append(memory)
                            else:
                                # Remove from index
                                memory_id = memory.get("memory_id")
                                if memory_id:
                                    self._memory_index.pop(memory_id, None)

                        # Update cleared count
                        cleared_count += original_count - len(memories_to_keep)

                        # Update partition
                        if len(memories_to_keep) == 0:
                            # Remove empty partition file
                            os.unlink(partition_file)
                        else:
                            # Save updated partition
                            partition_data["memories"] = memories_to_keep
                            self._save_partition(partition_file, partition_data)

                    except Exception as e:
                        logger.error(f"Failed to process partition {partition_file}: {e}")

        except Exception as e:
            logger.error(f"Failed to clear memories by context: {e}")

        return cleared_count

    def _clear_all(self) -> int:
        """Clear all memories."""
        try:
            with self._lock:
                # Count memories
                memory_count = len(self._memory_index)

                # Remove all partition files
                for partition_file in self.storage_path.glob("memories_*.json"):
                    os.unlink(partition_file)

                # Clear index
                self._memory_index.clear()

                return memory_count

        except Exception as e:
            logger.error(f"Failed to clear all memories: {e}")
            return 0
