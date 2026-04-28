import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SuggestionsManager:
    """Manages pending suggestions for the current workflow step."""

    def __init__(self):
        self._pending_suggestions: Optional[list[str]] = None
        self._suggestions_consumed = False

    def add_suggestions(self, suggestions: list[str]) -> None:
        """Add suggestions to be included in the next message."""

        self._pending_suggestions = suggestions
        self._suggestions_consumed = False

        logger.info(f"New pending suggestions: {self._pending_suggestions}")

    def get_and_consume_suggestions(self) -> Optional[list[str]]:
        """Get suggestions and mark them as consumed (one-time use)."""

        if self._pending_suggestions and not self._suggestions_consumed:
            suggestions = self._pending_suggestions
            self._suggestions_consumed = True
            return suggestions

        logger.info("No suggestions to return (either None or already consumed)")
        return None

    def clear_suggestions(self) -> None:
        """Clear all pending suggestions."""
        self._pending_suggestions = None
        self._suggestions_consumed = False
        logger.info("Suggestions cleared")


# Global instance
_suggestions_manager = SuggestionsManager()


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
