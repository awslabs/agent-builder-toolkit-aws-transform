# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for file_memory_repository module.
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext
from agent_builder_sdk.memory.file_memory_repository import FileSystemRepository


class TestFileSystemRepository:
    """Test cases for FileSystemRepository."""

    @pytest.fixture
    def temp_storage_path(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def repository(self, temp_storage_path):
        """Create a FileSystemRepository instance for testing."""
        return FileSystemRepository(temp_storage_path)

    @pytest.fixture
    def conversation_context(self):
        """Create a test conversation context."""
        return ConversationContext(
            user_id="test_user", conversation_id="test_conversation", agent_instance_id="test_agent"
        )

    @pytest.fixture
    def test_timestamp(self):
        """Create a test timestamp."""
        return datetime(2023, 1, 15, 12, 30, 45)

    def test_init_creates_storage_directory(self, temp_storage_path):
        """Test that initialization creates the storage directory."""
        storage_path = Path(temp_storage_path) / "new_dir"
        assert not storage_path.exists()

        repository = FileSystemRepository(str(storage_path))

        assert storage_path.exists()
        assert storage_path.is_dir()
        assert repository.storage_path == storage_path

    def test_init_with_existing_directory(self, temp_storage_path):
        """Test initialization with existing directory."""
        repository = FileSystemRepository(temp_storage_path)

        assert repository.storage_path == Path(temp_storage_path)
        assert repository._memory_index == {}

    def test_get_partition_file(self, repository):
        """Test _get_partition_file method."""
        test_date = date(2023, 1, 15)
        expected_path = repository.storage_path / "memories_2023-01-15.json"

        result = repository._get_partition_file(test_date)

        assert result == expected_path

    def test_load_partition_nonexistent_file(self, repository):
        """Test _load_partition with non-existent file."""
        partition_file = repository.storage_path / "memories_2023-01-15.json"

        result = repository._load_partition(partition_file)

        expected = {
            "date": "2023-01-15",
            "memories": [],
            "metadata": {
                "created": result["metadata"]["created"],  # Dynamic timestamp
                "memory_count": 0,
            },
        }
        assert result["date"] == expected["date"]
        assert result["memories"] == expected["memories"]
        assert result["metadata"]["memory_count"] == expected["metadata"]["memory_count"]
        assert "created" in result["metadata"]

    def test_load_partition_existing_file(self, repository):
        """Test _load_partition with existing file."""
        partition_file = repository.storage_path / "memories_2023-01-15.json"
        test_data = {
            "date": "2023-01-15",
            "memories": [{"memory_id": "test", "content": "test content"}],
            "metadata": {"created": "2023-01-15T12:00:00", "memory_count": 1},
        }

        # Create the file
        with open(partition_file, "w") as f:
            json.dump(test_data, f)

        result = repository._load_partition(partition_file)

        assert result == test_data

    def test_load_partition_corrupted_file(self, repository):
        """Test _load_partition with corrupted file."""
        partition_file = repository.storage_path / "memories_2023-01-15.json"

        # Create corrupted file
        with open(partition_file, "w") as f:
            f.write("invalid json")

        result = repository._load_partition(partition_file)

        # Should return empty partition structure
        assert result["date"] == "2023-01-15"
        assert result["memories"] == []
        assert result["metadata"]["memory_count"] == 0

    def test_save_partition(self, repository):
        """Test _save_partition method."""
        partition_file = repository.storage_path / "memories_2023-01-15.json"
        test_data = {
            "date": "2023-01-15",
            "memories": [{"memory_id": "test", "content": "test content"}],
            "metadata": {"created": "2023-01-15T12:00:00"},
        }

        result = repository._save_partition(partition_file, test_data)

        assert result is True
        assert partition_file.exists()

        # Verify file contents
        with open(partition_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data["date"] == test_data["date"]
        assert saved_data["memories"] == test_data["memories"]
        assert saved_data["metadata"]["memory_count"] == 1
        assert "last_updated" in saved_data["metadata"]

    def test_save_partition_write_error(self, repository):
        """Test _save_partition handles write errors."""
        partition_file = repository.storage_path / "memories_2023-01-15.json"
        test_data = {"date": "2023-01-15", "memories": [], "metadata": {}}

        # Make directory read-only to cause write error
        original_mode = repository.storage_path.stat().st_mode
        try:
            repository.storage_path.chmod(0o444)

            result = repository._save_partition(partition_file, test_data)

            assert result is False
        finally:
            repository.storage_path.chmod(original_mode)

    def test_store_success(self, repository, conversation_context, test_timestamp):
        """Test successful memory storage."""
        memory_id = "test_memory_id"
        content = "test content"
        metadata = {"key": "value"}

        result = repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content=content,
            metadata=metadata,
        )

        assert result is True
        assert memory_id in repository._memory_index
        assert repository._memory_index[memory_id] == test_timestamp.date()

        # Verify file was created
        partition_file = repository._get_partition_file(test_timestamp.date())
        assert partition_file.exists()

        # Verify file contents
        with open(partition_file, "r") as f:
            partition_data = json.load(f)

        assert len(partition_data["memories"]) == 1
        memory = partition_data["memories"][0]
        assert memory["memory_id"] == memory_id
        assert memory["content"] == content
        assert memory["metadata"] == metadata
        assert memory["timestamp"] == test_timestamp.isoformat()
        assert memory["context"]["user_id"] == conversation_context.user_id

    def test_store_overwrites_existing_memory(
        self, repository, conversation_context, test_timestamp
    ):
        """Test that storing with same memory_id overwrites existing memory."""
        memory_id = "test_memory_id"

        # Store first memory
        repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content="first content",
            metadata={"version": 1},
        )

        # Store second memory with same ID
        repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content="second content",
            metadata={"version": 2},
        )

        # Verify only one memory exists
        partition_file = repository._get_partition_file(test_timestamp.date())
        with open(partition_file, "r") as f:
            partition_data = json.load(f)

        assert len(partition_data["memories"]) == 1
        memory = partition_data["memories"][0]
        assert memory["content"] == "second content"
        assert memory["metadata"]["version"] == 2

    def test_store_file_write_error(self, repository, conversation_context, test_timestamp):
        """Test store handles file write errors gracefully."""
        memory_id = "test_memory_id"

        # Make storage directory read-only
        original_mode = repository.storage_path.stat().st_mode
        try:
            repository.storage_path.chmod(0o444)

            result = repository.store(
                memory_id=memory_id,
                timestamp=test_timestamp,
                context=conversation_context,
                content="test content",
            )

            assert result is False
            assert memory_id not in repository._memory_index
        finally:
            repository.storage_path.chmod(original_mode)

    def test_store_exception_handling(self, repository, conversation_context, test_timestamp):
        """Test store handles general exceptions."""
        memory_id = "test_memory_id"

        # Mock datetime.now to raise exception
        with patch(
            "agent_builder_sdk.memory.file_memory_repository.datetime"
        ) as mock_datetime:
            mock_datetime.now.side_effect = Exception("Time error")

            result = repository.store(
                memory_id=memory_id,
                timestamp=test_timestamp,
                context=conversation_context,
                content="test content",
            )

            assert result is False

    def test_retrieve_by_id_success(self, repository, conversation_context, test_timestamp):
        """Test successful retrieval by memory ID."""
        memory_id = "test_memory_id"
        content = "test content"

        # Store memory first
        repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content=content,
        )

        # Retrieve by ID
        result = repository.retrieve(memory_id=memory_id)

        assert len(result) == 1
        memory = result[0]
        assert memory["memory_id"] == memory_id
        assert memory["content"] == content

    def test_retrieve_by_id_not_found(self, repository):
        """Test retrieval by non-existent memory ID."""
        result = repository.retrieve(memory_id="nonexistent")

        assert result == []

    def test_retrieve_by_id_stale_index(self, repository, conversation_context, test_timestamp):
        """Test retrieval handles stale index entries."""
        memory_id = "test_memory_id"

        # Manually add to index without creating file
        repository._memory_index[memory_id] = test_timestamp.date()

        result = repository.retrieve(memory_id=memory_id)

        assert result == []
        assert memory_id not in repository._memory_index  # Should be cleaned up

    def test_retrieve_by_context(self, repository, conversation_context, test_timestamp):
        """Test retrieval by conversation context."""
        # Store multiple memories
        for i in range(3):
            repository.store(
                memory_id=f"memory_{i}",
                timestamp=test_timestamp,
                context=conversation_context,
                content=f"content {i}",
            )

        # Store memory with different context
        different_context = ConversationContext(
            user_id="different_user",
            conversation_id="different_conversation",
            agent_instance_id="different_agent",
        )
        repository.store(
            memory_id="different_memory",
            timestamp=test_timestamp,
            context=different_context,
            content="different content",
        )

        # Retrieve by original context
        result = repository.retrieve(context=conversation_context)

        assert len(result) == 3
        for memory in result:
            assert memory["context"]["user_id"] == conversation_context.user_id

    def test_retrieve_with_limit(self, repository, conversation_context, test_timestamp):
        """Test retrieval with limit parameter."""
        # Store multiple memories
        for i in range(5):
            repository.store(
                memory_id=f"memory_{i}",
                timestamp=test_timestamp,
                context=conversation_context,
                content=f"content {i}",
            )

        # Retrieve with limit
        result = repository.retrieve(context=conversation_context, limit=3)

        assert len(result) == 3

    def test_retrieve_handles_corrupted_partition(
        self, repository, conversation_context, test_timestamp
    ):
        """Test that retrieve handles corrupted partition files gracefully."""
        # Store a memory first
        repository.store(
            memory_id="test_memory",
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        # Corrupt the partition file
        partition_file = repository._get_partition_file(test_timestamp.date())
        with open(partition_file, "w") as f:
            f.write("invalid json")

        # Should handle gracefully and return empty list
        result = repository.retrieve(context=conversation_context)

        assert result == []

    def test_retrieve_exception_handling(self, repository):
        """Test retrieve handles general exceptions."""
        # Mock pathlib.Path.glob to raise exception
        with patch("pathlib.Path.glob", side_effect=Exception("Glob error")):
            result = repository.retrieve()

            assert result == []

    def test_clear_by_id_success(self, repository, conversation_context, test_timestamp):
        """Test successful clearing by memory ID."""
        memory_id = "test_memory_id"

        # Store memory first
        repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        # Clear by ID
        result = repository.clear(memory_id=memory_id)

        assert result == 1
        assert memory_id not in repository._memory_index

        # Verify memory is gone
        retrieved = repository.retrieve(memory_id=memory_id)
        assert retrieved == []

    def test_clear_by_id_not_found(self, repository):
        """Test clearing by non-existent memory ID."""
        result = repository.clear(memory_id="nonexistent")

        assert result == 0

    def test_clear_by_id_removes_empty_partition(
        self, repository, conversation_context, test_timestamp
    ):
        """Test that clearing last memory in partition removes the partition file."""
        memory_id = "test_memory_id"

        # Store single memory
        repository.store(
            memory_id=memory_id,
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        partition_file = repository._get_partition_file(test_timestamp.date())
        assert partition_file.exists()

        # Clear the memory
        result = repository.clear(memory_id=memory_id)

        assert result == 1
        assert not partition_file.exists()  # File should be removed

    def test_clear_by_context(self, repository, conversation_context, test_timestamp):
        """Test clearing by conversation context."""
        # Store memories with target context
        for i in range(3):
            repository.store(
                memory_id=f"target_memory_{i}",
                timestamp=test_timestamp,
                context=conversation_context,
                content=f"target content {i}",
            )

        # Store memory with different context
        different_context = ConversationContext(
            user_id="different_user",
            conversation_id="different_conversation",
            agent_instance_id="different_agent",
        )
        repository.store(
            memory_id="different_memory",
            timestamp=test_timestamp,
            context=different_context,
            content="different content",
        )

        # Clear by target context
        result = repository.clear(context=conversation_context)

        assert result == 3

        # Verify target memories are gone
        target_memories = repository.retrieve(context=conversation_context)
        assert len(target_memories) == 0

        # Verify different memory still exists
        different_memories = repository.retrieve(context=different_context)
        assert len(different_memories) == 1

    def test_clear_all(self, repository, conversation_context, test_timestamp):
        """Test clearing all memories."""
        # Store multiple memories
        for i in range(5):
            repository.store(
                memory_id=f"memory_{i}",
                timestamp=test_timestamp,
                context=conversation_context,
                content=f"content {i}",
            )

        # Clear all
        result = repository.clear()

        assert result == 5
        assert len(repository._memory_index) == 0

        # Verify all memories are gone
        all_memories = repository.retrieve()
        assert len(all_memories) == 0

    def test_clear_handles_corrupted_partition(
        self, repository, conversation_context, test_timestamp
    ):
        """Test that clear handles corrupted partition files gracefully."""
        # Store a memory first
        repository.store(
            memory_id="test_memory",
            timestamp=test_timestamp,
            context=conversation_context,
            content="test content",
        )

        # Corrupt the partition file
        partition_file = repository._get_partition_file(test_timestamp.date())
        with open(partition_file, "w") as f:
            f.write("invalid json")

        # Should handle gracefully
        result = repository.clear(context=conversation_context)

        # Should return 0 since it couldn't process the corrupted file
        assert result == 0

    def test_clear_exception_handling(self, repository):
        """Test clear handles general exceptions."""
        # Mock pathlib.Path.glob to raise exception
        with patch("pathlib.Path.glob", side_effect=Exception("Glob error")):
            result = repository.clear()

            assert result == 0

    def test_matches_context_exact_match(self, repository):
        """Test _matches_context with exact match."""
        memory_context = {
            "user_id": "test_user",
            "conversation_id": "test_conversation",
            "agent_instance_id": "test_agent",
        }
        conversation_context = ConversationContext(
            user_id="test_user", conversation_id="test_conversation", agent_instance_id="test_agent"
        )

        result = repository._matches_context(memory_context, conversation_context)

        assert result is True

    def test_matches_context_partial_match(self, repository):
        """Test _matches_context with partial match."""
        memory_context = {
            "user_id": "test_user",
            "conversation_id": "test_conversation",
            "agent_instance_id": "test_agent",
        }
        conversation_context = ConversationContext(
            user_id="test_user",
            conversation_id=None,  # None should match anything
            agent_instance_id=None,
        )

        result = repository._matches_context(memory_context, conversation_context)

        assert result is True

    def test_matches_context_no_match(self, repository):
        """Test _matches_context with no match."""
        memory_context = {
            "user_id": "test_user",
            "conversation_id": "test_conversation",
            "agent_instance_id": "test_agent",
        }
        conversation_context = ConversationContext(
            user_id="different_user",
            conversation_id="test_conversation",
            agent_instance_id="test_agent",
        )

        result = repository._matches_context(memory_context, conversation_context)

        assert result is False

    def test_load_index_with_existing_partitions(self, temp_storage_path):
        """Test _load_index with existing partition files."""
        # Create test partition files
        partition1_data = {
            "date": "2023-01-15",
            "memories": [
                {"memory_id": "memory1", "content": "content1"},
                {"memory_id": "memory2", "content": "content2"},
            ],
            "metadata": {"memory_count": 2},
        }
        partition2_data = {
            "date": "2023-01-16",
            "memories": [{"memory_id": "memory3", "content": "content3"}],
            "metadata": {"memory_count": 1},
        }

        partition1_file = Path(temp_storage_path) / "memories_2023-01-15.json"
        partition2_file = Path(temp_storage_path) / "memories_2023-01-16.json"

        with open(partition1_file, "w") as f:
            json.dump(partition1_data, f)
        with open(partition2_file, "w") as f:
            json.dump(partition2_data, f)

        # Create repository (which loads index)
        repository = FileSystemRepository(temp_storage_path)

        # Verify index was loaded correctly
        expected_index = {
            "memory1": date(2023, 1, 15),
            "memory2": date(2023, 1, 15),
            "memory3": date(2023, 1, 16),
        }
        assert repository._memory_index == expected_index

    def test_load_index_with_corrupted_partition(self, temp_storage_path):
        """Test _load_index handles corrupted partition files gracefully."""
        # Create valid partition
        partition1_data = {
            "date": "2023-01-15",
            "memories": [{"memory_id": "memory1", "content": "content1"}],
            "metadata": {"memory_count": 1},
        }
        partition1_file = Path(temp_storage_path) / "memories_2023-01-15.json"
        with open(partition1_file, "w") as f:
            json.dump(partition1_data, f)

        # Create corrupted partition
        partition2_file = Path(temp_storage_path) / "memories_2023-01-16.json"
        with open(partition2_file, "w") as f:
            f.write("invalid json")

        # Create repository (which loads index)
        repository = FileSystemRepository(temp_storage_path)

        # Verify only valid partition was loaded
        expected_index = {"memory1": date(2023, 1, 15)}
        assert repository._memory_index == expected_index

    def test_load_index_handles_missing_memory_id(self, temp_storage_path):
        """Test _load_index handles memories without memory_id gracefully."""
        partition_data = {
            "date": "2023-01-15",
            "memories": [
                {"memory_id": "valid_memory", "content": "content1"},
                {"content": "content2"},  # Missing memory_id
                {"memory_id": "", "content": "content3"},  # Empty memory_id
            ],
            "metadata": {"memory_count": 3},
        }

        partition_file = Path(temp_storage_path) / "memories_2023-01-15.json"
        with open(partition_file, "w") as f:
            json.dump(partition_data, f)

        # Create repository (which loads index)
        repository = FileSystemRepository(temp_storage_path)

        # Only valid memory should be in index
        expected_index = {"valid_memory": date(2023, 1, 15)}
        assert repository._memory_index == expected_index

    def test_load_index_handles_invalid_date_format(self, temp_storage_path):
        """Test _load_index handles invalid date formats in filenames gracefully."""
        # Create partition with invalid date format
        invalid_file = Path(temp_storage_path) / "memories_invalid-date.json"
        with open(invalid_file, "w") as f:
            json.dump({"memories": [{"memory_id": "test"}]}, f)

        # Create repository (which loads index)
        repository = FileSystemRepository(temp_storage_path)

        # Index should be empty since date parsing failed
        assert repository._memory_index == {}

    def test_concurrent_store_operations(self, repository, conversation_context, test_timestamp):
        """Test concurrent store operations are handled safely."""

        def store_memory(index):
            return repository.store(
                memory_id=f"memory_{index}",
                timestamp=test_timestamp,
                context=conversation_context,
                content=f"content {index}",
            )

        # Run concurrent store operations
        results = [store_memory(i) for i in range(10)]

        # All operations should succeed
        assert all(result is True for result in results)

        # All memories should be stored
        assert len(repository._memory_index) == 10

        # Verify all memories can be retrieved
        memories = repository.retrieve(context=conversation_context)
        assert len(memories) == 10

    def test_memory_ordering_by_timestamp(self, repository, conversation_context):
        """Test that memories are ordered by timestamp (newest first)."""
        timestamps = [
            datetime(2023, 1, 15, 10, 0, 0),
            datetime(2023, 1, 15, 12, 0, 0),
            datetime(2023, 1, 15, 11, 0, 0),
        ]

        # Store memories in non-chronological order
        for i, timestamp in enumerate(timestamps):
            repository.store(
                memory_id=f"memory_{i}",
                timestamp=timestamp,
                context=conversation_context,
                content=f"content at {timestamp.hour}:00",
            )

        # Retrieve memories
        memories = repository.retrieve(context=conversation_context)

        # Should be ordered by timestamp (newest first)
        assert len(memories) == 3
        assert "12:00" in memories[0]["content"]  # 12:00 (newest)
        assert "11:00" in memories[1]["content"]  # 11:00 (middle)
        assert "10:00" in memories[2]["content"]  # 10:00 (oldest)
