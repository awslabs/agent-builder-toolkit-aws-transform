"""
Unit tests for CheckpointService.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_builder_sdk.checkpoint.checkpoint_service import CheckpointService
from agent_builder_sdk.checkpoint.checkpoint_triggers import CheckpointStrategy
from agent_builder_sdk.server.server_models import AgentRuntimeContext


@pytest.fixture
def mock_context():
    """Create a mock AgentRuntimeContext."""
    return AgentRuntimeContext(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        initial_auth_token="test-token",
    )


@pytest.fixture
def checkpoint_service():
    """Create a CheckpointService instance."""
    return CheckpointService(
        storage_dir="/tmp/test", strategy=CheckpointStrategy.CONVERSATION, interval=5
    )


@pytest.fixture
def checkpoint_service_no_strategy():
    """Create a CheckpointService instance without strategy."""
    return CheckpointService(storage_dir="/tmp/test", strategy=None, interval=5)


class TestCheckpointServiceInitialization:
    """Test CheckpointService initialization."""

    def test_init_with_strategy(self):
        """Test initialization with strategy."""
        service = CheckpointService("/tmp/test", CheckpointStrategy.TIME, 30)

        assert service.storage_dir == "/tmp/test"
        assert service.strategy == CheckpointStrategy.TIME
        assert service.interval == 30
        assert service.manager is None
        assert service._background_task is None

    def test_init_without_strategy(self):
        """Test initialization without strategy."""
        service = CheckpointService("/tmp/test", None, 30)

        assert service.storage_dir == "/tmp/test"
        assert service.strategy is None
        assert service.interval == 30
        assert service.manager is None


class TestCheckpointServiceInitialize:
    """Test CheckpointService.initialize method."""

    @patch("agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository")
    @patch("agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager")
    @patch("agent_builder_sdk.checkpoint.checkpoint_service.ConversationTurnTrigger")
    def test_initialize_conversation_strategy(
        self, mock_trigger, mock_manager, mock_repo, checkpoint_service, mock_context
    ):
        """Test initialize with conversation strategy."""
        mock_repository = Mock()
        mock_repo.return_value = mock_repository

        checkpoint_service.initialize(mock_context)

        mock_repo.assert_called_once_with("/tmp/test", mock_context)
        mock_repository.restore_if_available.assert_called_once()
        mock_trigger.assert_called_once_with(turn_threshold=5)
        mock_manager.assert_called_once()
        assert checkpoint_service.manager is not None

    @patch("agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository")
    @patch("agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager")
    @patch("agent_builder_sdk.checkpoint.checkpoint_service.TimeBasedTrigger")
    def test_initialize_time_strategy(self, mock_trigger, mock_manager, mock_repo, mock_context):
        """Test initialize with time strategy."""
        service = CheckpointService("/tmp/test", CheckpointStrategy.TIME, 10)
        mock_repository = Mock()
        mock_repo.return_value = mock_repository

        service.initialize(mock_context)

        mock_trigger.assert_called_once_with(interval_minutes=10)
        mock_manager.assert_called_once()
        assert service.manager is not None

    @patch("agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository")
    def test_initialize_no_strategy(self, mock_repo, checkpoint_service_no_strategy, mock_context):
        """Test initialize without strategy."""
        mock_repository = Mock()
        mock_repo.return_value = mock_repository

        checkpoint_service_no_strategy.initialize(mock_context)

        mock_repository.restore_if_available.assert_called_once()
        assert checkpoint_service_no_strategy.manager is None

    @patch("agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository")
    def test_initialize_negative_interval(self, mock_repo, mock_context):
        """Test initialize with negative interval."""
        service = CheckpointService("/tmp/test", CheckpointStrategy.CONVERSATION, -5)
        mock_repository = Mock()
        mock_repo.return_value = mock_repository

        service.initialize(mock_context)

        mock_repository.restore_if_available.assert_called_once()
        assert service.manager is None  # Should not create manager with negative interval

    def test_initialize_invalid_strategy(self, mock_context):
        """Test initialize with invalid strategy."""
        service = CheckpointService("/tmp/test", "invalid", 5)

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ) as mock_repo:
            mock_repository = Mock()
            mock_repo.return_value = mock_repository

            service.initialize(mock_context)  # Should not raise, just log warning
            assert service.manager is None

    @patch("agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository")
    def test_initialize_exception_handling(self, mock_repo, checkpoint_service, mock_context):
        """Test initialize handles exceptions gracefully."""
        mock_repo.side_effect = Exception("Test error")

        checkpoint_service.initialize(mock_context)  # Should not raise
        assert checkpoint_service.manager is None


class TestCheckpointServiceCallback:
    """Test CheckpointService.create_callback method."""

    def test_create_callback_no_manager(self, checkpoint_service):
        """Test create_callback when no manager exists."""
        callback = checkpoint_service.create_callback()
        assert callback is None

    def test_create_callback_wrong_trigger_type(self, checkpoint_service, mock_context):
        """Test create_callback with non-conversation trigger."""
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ), patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager"
        ) as mock_manager_class:

            # Use real TimeBasedTrigger instead of mocking it
            from agent_builder_sdk.checkpoint.checkpoint_triggers import TimeBasedTrigger

            service = CheckpointService("/tmp/test", CheckpointStrategy.TIME, 10)
            mock_manager = Mock()
            mock_manager.trigger = TimeBasedTrigger(interval_minutes=10)
            mock_manager_class.return_value = mock_manager

            service.initialize(mock_context)
            callback = service.create_callback()

            assert callback is None

    def test_create_callback_conversation_trigger(self, checkpoint_service, mock_context):
        """Test create_callback with conversation trigger."""
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ), patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager"
        ) as mock_manager_class:

            # Use real ConversationTurnTrigger instead of mocking it
            from agent_builder_sdk.checkpoint.checkpoint_triggers import (
                ConversationTurnTrigger,
            )

            mock_trigger = ConversationTurnTrigger(turn_threshold=5)
            mock_manager = Mock()
            mock_manager.trigger = mock_trigger
            mock_manager_class.return_value = mock_manager

            checkpoint_service.initialize(mock_context)
            callback = checkpoint_service.create_callback()

            assert callback is not None

            # Test callback execution
            callback()
            # Note: We can't easily assert increment_turn was called since it's a real object


class TestCheckpointServiceBackgroundTask:
    """Test CheckpointService background checkpointing."""

    @pytest.mark.asyncio
    async def test_start_background_checkpointing_no_manager(self, checkpoint_service):
        """Test start_background_checkpointing when no manager exists."""
        await checkpoint_service.start_background_checkpointing()
        assert checkpoint_service._background_task is None

    @pytest.mark.asyncio
    async def test_start_background_checkpointing_with_manager(
        self, checkpoint_service, mock_context
    ):
        """Test start_background_checkpointing with manager."""
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ), patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager"
        ) as mock_manager_class, patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.ConversationTurnTrigger"
        ):

            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            checkpoint_service.initialize(mock_context)
            await checkpoint_service.start_background_checkpointing()

            assert checkpoint_service._background_task is not None
            assert not checkpoint_service._background_task.done()

            # Clean up
            checkpoint_service._background_task.cancel()
            try:
                await checkpoint_service._background_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_background_task_calls_attempt_checkpoint(self, checkpoint_service, mock_context):
        """Test that background task calls attempt_checkpoint."""
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ), patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager"
        ) as mock_manager_class, patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.ConversationTurnTrigger"
        ), patch(
            "asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:

            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            checkpoint_service.initialize(mock_context)
            await checkpoint_service.start_background_checkpointing()

            # Let the task run once
            mock_sleep.side_effect = [None, asyncio.CancelledError()]

            try:
                await checkpoint_service._background_task
            except asyncio.CancelledError:
                pass

            mock_manager.attempt_checkpoint.assert_called()


class TestCheckpointServiceShutdown:
    """Test CheckpointService.shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_no_background_task(self, checkpoint_service):
        """Test shutdown when no background task exists."""
        await checkpoint_service.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown_no_manager(self, checkpoint_service):
        """Test shutdown when no manager exists."""
        checkpoint_service._background_task = Mock()
        checkpoint_service._background_task.done.return_value = True

        await checkpoint_service.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown_with_background_task_and_manager(
        self, checkpoint_service, mock_context
    ):
        """Test shutdown with background task and manager."""
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.create_checkpoint_repository"
        ), patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.CheckpointManager"
        ) as mock_manager_class, patch(
            "agent_builder_sdk.checkpoint.checkpoint_service.ConversationTurnTrigger"
        ):

            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            checkpoint_service.initialize(mock_context)
            await checkpoint_service.start_background_checkpointing()

            await checkpoint_service.shutdown()

            # Verify cleanup
            assert checkpoint_service._background_task.done()
            mock_manager.force_checkpoint.assert_called_once()
            assert checkpoint_service.manager is None

    @pytest.mark.asyncio
    async def test_shutdown_handles_exceptions(self, checkpoint_service):
        """Test shutdown handles exceptions gracefully."""
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel.side_effect = Exception("Test error")
        checkpoint_service._background_task = mock_task

        await checkpoint_service.shutdown()  # Should not raise
