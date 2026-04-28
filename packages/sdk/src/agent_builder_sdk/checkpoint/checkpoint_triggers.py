"""
Checkpoint trigger strategies for agent state/memory/conversation persistence.
"""

import threading
import time
from abc import ABC, abstractmethod
from enum import Enum


class CheckpointStrategy(Enum):
    """Checkpoint strategy options."""

    CONVERSATION = "conversation"  # Checkpoint every N conversation turns
    TIME = "time"  # Checkpoint every N minutes


class CheckpointTrigger(ABC):
    """Base class for checkpoint triggers"""

    @abstractmethod
    def should_checkpoint(self) -> bool:
        """Check if checkpoint should be triggered"""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset trigger state after checkpoint"""
        pass


class TimeBasedTrigger(CheckpointTrigger):
    """Trigger checkpoint based on time interval"""

    def __init__(self, interval_minutes: int = 30):
        self.interval_second = interval_minutes * 60
        self.last_checkpoint_time = time.monotonic()

    def should_checkpoint(self) -> bool:
        """Check if enough time has passed last checkpoints"""
        return (time.monotonic() - self.last_checkpoint_time) >= self.interval_second

    def reset(self) -> None:
        """Reset the timer"""
        self.last_checkpoint_time = time.monotonic()


class ConversationTurnTrigger(CheckpointTrigger):
    """Trigger checkpoint based on conversation turns"""

    def __init__(self, turn_threshold: int = 20):
        self.turn_threshold = turn_threshold
        self.current_turn = 0
        self._lock = threading.Lock()

    def should_checkpoint(self) -> bool:
        """Check if turn threshold is reached"""
        with self._lock:
            return self.current_turn >= self.turn_threshold

    def increment_turn(self):
        """Increment conversation turn counter (thread-safe)"""
        with self._lock:
            self.current_turn += 1

    def reset(self) -> None:
        """Reset turn counter"""
        with self._lock:
            self.current_turn = 0
