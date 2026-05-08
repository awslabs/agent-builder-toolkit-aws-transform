# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for checkpoint manager.
"""

from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.checkpoint.checkpoint_manager import (
    BackgroundCheckpointer,
    CheckpointManager,
)
from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    ConversationTurnTrigger,
    TimeBasedTrigger,
)


@pytest.fixture
def mock_checkpoint_repository():
    """Mock CheckpointRepository for testing."""
    return Mock()


@pytest.fixture
def mock_trigger():
    """Mock CheckpointTrigger for testing."""
    return Mock()


@pytest.fixture
def manager(mock_checkpoint_repository, mock_trigger):
    """Create CheckpointManager with mocked dependencies."""
    return CheckpointManager(mock_checkpoint_repository, mock_trigger)


@pytest.fixture
def background_checkpointer(manager):
    """Create BackgroundCheckpointer with mocked manager."""
    return BackgroundCheckpointer(manager, check_interval=1)


class TestCheckpointManager:
    """Test CheckpointManager functionality."""

    def test_execute_checkpoint_with_existing_checkpoint(self, manager, mock_checkpoint_repository):
        """Test _execute_checkpoint when checkpoint exists."""
        # Mock existing checkpoint
        existing_checkpoint = {"artifactId": "existing-123"}
        mock_checkpoint_repository.list_checkpoint.return_value = [existing_checkpoint]
        mock_checkpoint_repository.update_checkpoint.return_value = True

        result = manager._execute_checkpoint()

        assert result is True
        mock_checkpoint_repository.list_checkpoint.assert_called_once()
        mock_checkpoint_repository.update_checkpoint.assert_called_once_with(
            existing_checkpoint=existing_checkpoint
        )

    def test_execute_checkpoint_without_existing_checkpoint(
        self, manager, mock_checkpoint_repository
    ):
        """Test _execute_checkpoint when no checkpoint exists."""
        # Mock no existing checkpoint
        mock_checkpoint_repository.list_checkpoint.return_value = []
        mock_checkpoint_repository.create_checkpoint.return_value = "new-artifact-123"

        result = manager._execute_checkpoint()

        assert result is True
        mock_checkpoint_repository.list_checkpoint.assert_called_once()
        mock_checkpoint_repository.create_checkpoint.assert_called_once()

    def test_execute_checkpoint_create_fails(self, manager, mock_checkpoint_repository):
        """Test _execute_checkpoint when create_checkpoint returns None."""
        # Mock no existing checkpoint and create fails
        mock_checkpoint_repository.list_checkpoint.return_value = []
        mock_checkpoint_repository.create_checkpoint.return_value = None

        result = manager._execute_checkpoint()

        assert result is False

    def test_attempt_checkpoint_when_should_checkpoint_true(
        self, manager, mock_trigger, mock_checkpoint_repository
    ):
        """Test attempt_checkpoint when trigger says should checkpoint."""
        mock_trigger.should_checkpoint.return_value = True
        mock_checkpoint_repository.list_checkpoint.return_value = []
        mock_checkpoint_repository.create_checkpoint.return_value = "artifact-123"

        result = manager.attempt_checkpoint()

        assert result is True
        mock_trigger.should_checkpoint.assert_called_once()
        mock_trigger.reset.assert_called_once()

    def test_attempt_checkpoint_when_should_checkpoint_false(self, manager, mock_trigger):
        """Test attempt_checkpoint when trigger says should not checkpoint."""
        mock_trigger.should_checkpoint.return_value = False

        result = manager.attempt_checkpoint()

        assert result is False
        mock_trigger.should_checkpoint.assert_called_once()
        mock_trigger.reset.assert_not_called()

    def test_attempt_checkpoint_with_exception(
        self, manager, mock_trigger, mock_checkpoint_repository
    ):
        """Test attempt_checkpoint handles exceptions."""
        mock_trigger.should_checkpoint.return_value = True
        mock_checkpoint_repository.list_checkpoint.side_effect = Exception("Test error")

        result = manager.attempt_checkpoint()

        assert result is False
        mock_trigger.should_checkpoint.assert_called_once()
        # Trigger should not be reset when exception occurs
        mock_trigger.reset.assert_not_called()

    def test_force_checkpoint_success(self, manager, mock_checkpoint_repository):
        """Test force_checkpoint success."""
        mock_checkpoint_repository.list_checkpoint.return_value = []
        mock_checkpoint_repository.create_checkpoint.return_value = "artifact-123"

        result = manager.force_checkpoint()

        assert result is True

    def test_force_checkpoint_failure(self, manager, mock_checkpoint_repository):
        """Test force_checkpoint failure."""
        mock_checkpoint_repository.list_checkpoint.return_value = []
        mock_checkpoint_repository.create_checkpoint.return_value = None

        result = manager.force_checkpoint()

        assert result is False

    def test_force_checkpoint_with_exception(self, manager, mock_checkpoint_repository):
        """Test force_checkpoint handles exceptions."""
        mock_checkpoint_repository.list_checkpoint.side_effect = Exception("Test error")

        result = manager.force_checkpoint()

        assert result is False


class TestCheckpointManagerRestoreVerification:
    """Test restore verification guard in CheckpointManager."""

    def test_blocks_write_and_attempts_late_restore(self):
        """Blocks writes when restore not verified, attempts late restore."""
        repo = Mock()
        repo.is_restore_verified = False
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        # Late restore succeeds (sets is_restore_verified to True via side_effect)
        def restore_side_effect():
            repo.is_restore_verified = True
            return True

        repo.restore_if_available.side_effect = restore_side_effect
        repo.list_checkpoint.return_value = []
        repo.create_checkpoint.return_value = "artifact-123"

        result = manager._execute_checkpoint()

        assert result is True
        repo.restore_if_available.assert_called_once()

    def test_proceeds_after_successful_late_restore(self):
        """Proceeds with checkpoint after successful late restore."""
        repo = Mock()
        repo.is_restore_verified = False
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        def restore_side_effect():
            repo.is_restore_verified = True
            return True

        repo.restore_if_available.side_effect = restore_side_effect
        existing_checkpoint = {"artifactId": "existing-123"}
        repo.list_checkpoint.return_value = [existing_checkpoint]
        repo.update_checkpoint.return_value = True

        result = manager._execute_checkpoint()

        assert result is True
        repo.update_checkpoint.assert_called_once_with(existing_checkpoint=existing_checkpoint)

    def test_skips_without_retry_after_failed_late_restore(self):
        """Skips without retrying on subsequent calls after failed late restore."""
        repo = Mock()
        repo.is_restore_verified = False
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        # Late restore fails (is_restore_verified stays False)
        repo.restore_if_available.return_value = False

        # First call — attempts late restore, fails, skips
        result1 = manager._execute_checkpoint()
        assert result1 is False
        repo.restore_if_available.assert_called_once()

        # Second call — skips immediately without retrying
        result2 = manager._execute_checkpoint()
        assert result2 is False
        # Still only called once (no retry)
        repo.restore_if_available.assert_called_once()

    def test_proceeds_normally_when_restore_verified(self):
        """Works normally when restore is already verified."""
        repo = Mock()
        repo.is_restore_verified = True
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        repo.list_checkpoint.return_value = []
        repo.create_checkpoint.return_value = "artifact-123"

        result = manager._execute_checkpoint()

        assert result is True
        repo.restore_if_available.assert_not_called()

    def test_force_checkpoint_respects_guard(self):
        """force_checkpoint() also respects the restore verification guard."""
        repo = Mock()
        repo.is_restore_verified = False
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        # Late restore fails
        repo.restore_if_available.return_value = False

        result = manager.force_checkpoint()

        assert result is False
        repo.restore_if_available.assert_called_once()

    def test_late_restore_exception_caught_gracefully(self):
        """Exceptions during late restore are caught gracefully."""
        repo = Mock()
        repo.is_restore_verified = False
        trigger = Mock()
        manager = CheckpointManager(repo, trigger)

        repo.restore_if_available.side_effect = Exception("Auth still broken")

        result = manager._execute_checkpoint()

        assert result is False
        repo.restore_if_available.assert_called_once()


class TestBackgroundCheckpointer:
    """Test BackgroundCheckpointer functionality."""

    def test_init(self, background_checkpointer, manager):
        """Test initialization."""
        assert background_checkpointer.manager == manager
        assert background_checkpointer.check_interval == 1
        assert background_checkpointer.enabled is False
        assert background_checkpointer.task is None

    def test_enable(self, background_checkpointer):
        """Test enabling background checkpointer."""
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = Mock()
            mock_create_task.return_value = mock_task

            background_checkpointer.enable()

            assert background_checkpointer.enabled is True
            assert background_checkpointer.task == mock_task
            mock_create_task.assert_called_once()

    def test_disable(self, background_checkpointer):
        """Test disabling background checkpointer."""
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = Mock()
            mock_create_task.return_value = mock_task

            # First enable it
            background_checkpointer.enable()
            assert background_checkpointer.enabled is True

            # Then disable
            background_checkpointer.disable()
            assert background_checkpointer.enabled is False

    @pytest.mark.asyncio
    async def test_shutdown(self, background_checkpointer):
        """Test graceful shutdown."""
        # Enable first
        background_checkpointer.enable()

        # Shutdown
        await background_checkpointer.shutdown()

        assert background_checkpointer.enabled is False

    def test_increment_conversation_turn_with_conversation_trigger(self, manager):
        """Test increment_conversation_turn with ConversationTurnTrigger."""

        # Set up conversation trigger
        conv_trigger = Mock(spec=ConversationTurnTrigger)
        manager.trigger = conv_trigger

        background_checkpointer = BackgroundCheckpointer(manager)
        background_checkpointer.increment_conversation_turn()

        conv_trigger.increment_turn.assert_called_once()

    def test_increment_conversation_turn_with_time_trigger(self, manager):
        """Test increment_conversation_turn with TimeBasedTrigger."""

        # Set up time trigger
        time_trigger = Mock(spec=TimeBasedTrigger)
        manager.trigger = time_trigger

        background_checkpointer = BackgroundCheckpointer(manager)
        background_checkpointer.increment_conversation_turn()

        # Should not call increment_turn for time-based trigger
        assert not hasattr(time_trigger, "increment_turn") or not time_trigger.increment_turn.called
