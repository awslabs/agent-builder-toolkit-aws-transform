# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint management for agent state/memory/conversation persistence.
"""

import asyncio
import logging
from typing import Optional

from agent_builder_sdk.checkpoint.checkpoint_repository import CheckpointRepository
from agent_builder_sdk.checkpoint.checkpoint_triggers import (
    CheckpointTrigger,
    ConversationTurnTrigger,
)

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoint operations based on triggers."""

    def __init__(self, checkpoint_repository: CheckpointRepository, trigger: CheckpointTrigger):
        self.checkpoint_repository = checkpoint_repository
        self.trigger = trigger
        # Tracks whether we've already retried restore after an unverified startup,
        # so a persistently failing restore doesn't retry on every checkpoint tick.
        self._late_restore_attempted = False

    def _execute_checkpoint(self) -> bool:
        """Execute checkpoint creation/update logic."""
        # Guard against overwriting remote state when startup restore never succeeded.
        # During container startup the initial restore can race the auth-credential
        # update and fail; without this guard the next checkpoint would clobber the
        # existing good remote checkpoint with empty local state. We retry restore
        # once here, and refuse to write if it still hasn't been verified.
        if not self.checkpoint_repository.is_restore_verified:
            if not self._late_restore_attempted:
                self._late_restore_attempted = True
                try:
                    self.checkpoint_repository.restore_if_available()
                except Exception:
                    logger.warning("Late restore attempt failed:", exc_info=True)
                if not self.checkpoint_repository.is_restore_verified:
                    logger.warning(
                        "Skipping checkpoint: restore never verified, "
                        "refusing to overwrite remote state"
                    )
                    return False
            else:
                logger.warning(
                    "Skipping checkpoint: restore never verified and "
                    "late restore already attempted"
                )
                return False

        checkpoints = self.checkpoint_repository.list_checkpoint()
        if checkpoints:
            success = self.checkpoint_repository.update_checkpoint(
                existing_checkpoint=checkpoints[0]
            )
        else:
            artifact_id = self.checkpoint_repository.create_checkpoint()
            success = artifact_id is not None
        return success

    def attempt_checkpoint(self) -> bool:
        """Attempt to create a checkpoint if trigger conditions are met."""
        if self.trigger.should_checkpoint():
            try:
                success = self._execute_checkpoint()

                # Reset trigger regardless of success/failure since attempt was made
                self.trigger.reset()

                if success:
                    logger.info("Checkpoint completed successfully")
                else:
                    logger.info("Checkpoint attempt completed but failed")

                return success

            except Exception:
                logger.warning("Checkpointing error:", exc_info=True)
                return False

        return False

    def force_checkpoint(self) -> bool:
        """Force a checkpoint creation bypassing trigger conditions."""
        try:
            success = self._execute_checkpoint()

            if success:
                logger.info("Force checkpoint completed successfully")
            else:
                logger.error("Force checkpoint failed")

            return success

        except Exception:
            logger.warning("Force checkpoint error:", exc_info=True)
            return False


class BackgroundCheckpointer:
    """Background checkpointing with runtime configuration."""

    def __init__(self, manager: CheckpointManager, check_interval: int = 60):
        self.manager = manager
        self.check_interval = check_interval
        self.enabled = False
        self.task: Optional[asyncio.Task] = None

    def enable(self) -> None:
        """Enable background checkpointing."""
        if not self.enabled:
            self.enabled = True
            self.task = asyncio.create_task(self._background_loop())
            logger.info("Background checkpointing enabled")

    def disable(self) -> None:
        """Disable background checkpointing."""
        if self.enabled:
            self.enabled = False
            if self.task and not self.task.done():
                self.task.cancel()
                logger.info("Background checkpointing task cancelled")
            logger.info("Background checkpointing disabled")

    async def shutdown(self) -> None:
        """Graceful shutdown without final checkpoint."""
        if self.enabled:
            logger.info("Shutting down background checkpointer...")

            # Disable background processing
            self.disable()

            # Wait for task to complete in 10 seconds
            if self.task and not self.task.done():
                try:
                    await asyncio.wait_for(self.task, timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning("Background checkpointer shutdown timed out")
                except asyncio.CancelledError:
                    pass

    async def _background_loop(self) -> None:
        """Background checkpoint loop."""
        while self.enabled:
            try:
                self.manager.attempt_checkpoint()
                # sleep 30s
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Background checkpoint error:", exc_info=True)

    def increment_conversation_turn(self) -> None:
        """Increment conversation turn if using ConversationTurnTrigger."""

        if isinstance(self.manager.trigger, ConversationTurnTrigger):
            self.manager.trigger.increment_turn()
