"""Decorators for marking experimental APIs."""

import warnings
from functools import wraps
from typing import Any


def experimental(
    message: str = "This is experimental and subject to breaking changes",
) -> Any:
    """
    Decorator to mark classes or functions as experimental.

    Emits a FutureWarning when the decorated item is instantiated or called.

    Args:
        message: Custom warning message (optional)

    Example:
        @experimental("TaskManager may change in future versions")
        class TaskManager:
            pass
    """

    def decorator(obj: Any) -> Any:
        if isinstance(obj, type):
            # Decorating a class - wrap __init__
            original_init = obj.__init__  # type: ignore[misc]

            @wraps(original_init)
            def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
                warnings.warn(f"{obj.__name__}: {message}", FutureWarning, stacklevel=2)
                original_init(self, *args, **kwargs)

            obj.__init__ = new_init  # type: ignore[misc]
            return obj
        else:
            # Decorating a function
            @wraps(obj)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                warnings.warn(f"{obj.__name__}: {message}", FutureWarning, stacklevel=2)
                return obj(*args, **kwargs)

            return wrapper

    return decorator
