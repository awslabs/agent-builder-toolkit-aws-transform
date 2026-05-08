# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint service for managing agent checkpoint lifecycle.
"""

import asyncio
import logging
from typing import Callable, Optional

from agent_builder_sdk.checkpoint.checkpoint_manager import CheckpointManager
from agent_builder_sdk.checkpoint.checkpoint_repository import create_checkpoint_repository
from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    CheckpointStrategy,
    CheckpointTrigger,
    ConversationTurnTrigger,
    TimeBasedTrigger,
)
from agent_builder_sdk.server.server_models import AgentRuntimeContext

logger = logging.getLogger(__name__)


class CheckpointService:
    """Manages checkpoint lifecycle for agent runtime."""

    def __init__(
        self,
        storage_dir: str,
        strategy: Optional[CheckpointStrategy] = None,
        interval: int = 30,
    ):
        """
        Initialize checkpoint service.

        Args:
            storage_dir: Base directory for checkpoint storage
            strategy: Checkpoint strategy enum (optional)
            interval: Checkpoint interval - turns or minutes (default: 30)
        """
        self.storage_dir = storage_dir
        self.strategy = strategy
        self.interval = interval
        self.manager: Optional[CheckpointManager] = None
        self._background_task: Optional[asyncio.Task] = None
        self.was_restored: bool = False

    def initialize(self, context: AgentRuntimeContext) -> None:
        """Initialize checkpoint manager and restore if available."""
        try:
            # Create repository and restore if available
            checkpoint_repository = create_checkpoint_repository(self.storage_dir, context)
            self.was_restored = checkpoint_repository.restore_if_available()

            if not self.strategy or self.interval < 0:
                logger.info(
                    "Checkpointing is disabled, checkpoint strategy is not provided or interval is invalid "
                )
                return

            # Create trigger based on strategy
            trigger: CheckpointTrigger
            if self.strategy == CheckpointStrategy.CONVERSATION:
                trigger = ConversationTurnTrigger(turn_threshold=self.interval)
            elif self.strategy == CheckpointStrategy.TIME:
                trigger = TimeBasedTrigger(interval_minutes=self.interval)
            else:
                raise ValueError(f"Unknown checkpoint strategy: {self.strategy}")

            self.manager = CheckpointManager(checkpoint_repository, trigger)
            logger.info(
                f"Checkpointing enabled: {self.strategy} strategy, interval: {self.interval}, "
                f"checkpointing_path: {self.storage_dir}"
            )

        except Exception:
            logger.warning("Failed to initialize checkpointing:", exc_info=True)

    def create_callback(self) -> Optional[Callable]:
        """Create checkpoint callback for conversation-based checkpointing."""
        if not self.manager or not isinstance(self.manager.trigger, ConversationTurnTrigger):
            logger.info("No checkpoint callback created - conversation checkpointing not enabled")
            return None

        logger.info("Creating conversation checkpoint callback")

        def callback():
            # Type assertion since we already checked isinstance above
            assert self.manager is not None
            assert isinstance(self.manager.trigger, ConversationTurnTrigger)
            # Only increment turn - background task will handle actual checkpointing
            self.manager.trigger.increment_turn()
            logger.info(f"current turn: {self.manager.trigger.current_turn}")

        return callback

    async def start_background_checkpointing(self) -> None:
        """Start background checkpoint task."""
        if not self.manager:
            return

        async def background_checkpoint():
            while True:
                await asyncio.sleep(10)  # Check every 10 seconds
                try:
                    if self.manager:
                        self.manager.attempt_checkpoint()
                except Exception:
                    logger.warning("Background checkpoint error:", exc_info=True)

        self._background_task = asyncio.create_task(background_checkpoint())
        logger.info("Background checkpointing task started")

    async def shutdown(self) -> None:
        """Cleanup and final checkpoint."""
        logger.info("Shutting down checkpoint service...")

        try:
            # Cancel background checkpoint task
            if self._background_task and not self._background_task.done():
                logger.info("Stopping background checkpointing...")
                self._background_task.cancel()
                try:
                    await self._background_task
                except asyncio.CancelledError:
                    logger.info("Background checkpointing stopped")

            # Create final checkpoint (force checkpoint regardless of trigger)
            if self.manager:
                logger.info("Creating final checkpoint before shutdown...")
                success = self.manager.force_checkpoint()
                if not success:
                    logger.warning("Final checkpoint failed")

            # Cleanup checkpoint manager
            if self.manager:
                logger.info("Stopping checkpoint manager...")
                self.manager = None

            logger.info("Checkpoint service shutdown completed")

        except Exception:
            logger.exception("Error during checkpoint service shutdown")
