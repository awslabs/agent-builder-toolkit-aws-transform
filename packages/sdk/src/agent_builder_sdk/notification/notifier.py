__all__ = ("Notifier",)

from typing import Protocol, TypeVar

from agent_builder_sdk.custom_types.notification_types import NotificationDetail

T = TypeVar("T", bound=NotificationDetail, contravariant=True)


class Notifier(Protocol[T]):
    def notify(self, notification: T) -> bool:
        """Notify the waiter, if any, of the notification.

        Return true if there is a waiter for the notification.
        """
