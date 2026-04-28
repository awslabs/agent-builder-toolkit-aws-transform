"""
Notification handler for the ATX Base Agent.

Supports registerable processors for different notification types, similar to Strands hooks.
"""

import logging
from typing import Dict

from agent_builder_sdk.custom_types.notification_types import Notification, NotificationType
from agent_builder_sdk.message_queue import QueueService

from .notification_processor import NotificationProcessor

logger = logging.getLogger(__name__)


class NotificationHandler:
    """Handles notifications using registerable processors, similar to Strands hooks."""

    def __init__(self, queue: QueueService):
        self._queue = queue
        self._processors: Dict[NotificationType, NotificationProcessor] = {}

    def register_processor(
        self, notification_type: NotificationType, processor: NotificationProcessor
    ):
        """Register a processor for a notification type.

        Args:
            notification_type: The notification type to handle
            processor: Processor instance
        """
        # Only inject queue if processor has queue attribute
        if hasattr(processor, "queue"):
            processor.queue = self._queue
        self._processors[notification_type] = processor
        logger.info(f"Registered {processor.__class__.__name__} for {notification_type.value}")

    async def handle_notification(self, request: dict[str, str]) -> dict[str, str]:
        """Handle notification invocations from the platform.

        Args:
            request: The notification request containing type and details

        Returns:
            Dict containing the response message and any relevant data
        """
        logger.info(f"Received notification invocation {request}")

        try:
            notification = Notification.from_dict(request)

            # Run the registered processor for this notification type
            if processor := self._processors.get(notification.notification_type):
                return await processor.process(notification)
            else:
                logger.info(f"No processor registered for {notification.notification_type.value}")
                return {
                    "message": f"Notification received: {notification.notification_type.value}",
                    "notificationType": notification.notification_type.value,
                }

        except Exception as e:
            logger.exception(f"Error processing notification: {e}")
            return {
                "message": "Error processing notification",
                "error": str(e),
                "notificationType": request.get("type", request.get("notificationType", "")),
            }
