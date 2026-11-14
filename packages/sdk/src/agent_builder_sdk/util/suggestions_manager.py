# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)


class _Holder:
    """Mutable suggestion state (pending list + one-time-consumed flag)."""

    __slots__ = ("pending", "consumed")

    def __init__(self) -> None:
        self.pending: Optional[list[str]] = None
        self.consumed: bool = False


class SuggestionsManager:
    """Manages pending suggestions for the current message.

    Storage is a plain shared holder by default — the behavior used by the message/send path
    (served by the shared singleton agent), which the single worker queue serializes to one
    turn at a time. A plain object attribute (unlike a ContextVar) is visible both from the
    worker thread that runs the agent (via ``asyncio.to_thread``) and from the request task
    that reads the result, so the suggestion set by a tool survives that boundary.

    For concurrent streaming (N per-user agents' turns run inline on one event loop, with no
    queue serialization) a turn may call ``begin_turn_scope()`` to bind a per-turn holder in a
    ContextVar. When a scope is active, add/get/clear operate on that turn-local holder instead
    of the shared one, so concurrent turns can't clobber or double-consume each other's
    suggestions (nor leak into a concurrent message/send turn). The message/send path never
    opens a scope, so it keeps using the shared holder — behavior unchanged.
    """

    def __init__(self) -> None:
        self._shared = _Holder()
        self._scope: ContextVar[Optional[_Holder]] = ContextVar("suggestions_scope", default=None)

    def _holder(self) -> _Holder:
        scoped = self._scope.get()
        return scoped if scoped is not None else self._shared

    def begin_turn_scope(self) -> None:
        """Isolate suggestions to the current turn (concurrent streaming path).

        Sets a fresh per-turn holder in a ContextVar. Because each streaming turn runs in
        its own asyncio task, this holder is visible only within that turn. The message/send
        path never calls this, so it continues to use the shared holder.
        """
        self._scope.set(_Holder())

    def add_suggestions(self, suggestions: list[str]) -> None:
        """Add suggestions to be included in the next message."""
        holder = self._holder()
        holder.pending = suggestions
        holder.consumed = False
        logger.info(f"New pending suggestions: {suggestions}")

    def get_and_consume_suggestions(self) -> Optional[list[str]]:
        """Get suggestions and mark them as consumed (one-time use)."""
        holder = self._holder()
        if holder.pending and not holder.consumed:
            holder.consumed = True
            return holder.pending

        logger.info("No suggestions to return (either None or already consumed)")
        return None

    def clear_suggestions(self) -> None:
        """Clear all pending suggestions."""
        holder = self._holder()
        holder.pending = None
        holder.consumed = False
        logger.info("Suggestions cleared")


# Global instance.
_suggestions_manager = SuggestionsManager()


def begin_turn_scope() -> None:
    """Open a per-turn suggestion scope (concurrent streaming). The message/send path never
    calls it, so its shared-holder behavior is unchanged."""
    _suggestions_manager.begin_turn_scope()


def add_suggestions(suggestions: list[str]) -> None:
    """Add suggestions for the next message."""
    _suggestions_manager.add_suggestions(suggestions)


def get_and_consume_suggestions() -> Optional[list[str]]:
    """Get and consume pending suggestions."""
    result = _suggestions_manager.get_and_consume_suggestions()
    return result


def clear_suggestions() -> None:
    """Clear pending suggestions."""
    _suggestions_manager.clear_suggestions()
