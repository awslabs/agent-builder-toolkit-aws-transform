# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Base protocol for notification processors."""

from typing import Protocol

from agent_builder_sdk.custom_types.notification_types import Notification


class NotificationProcessor(Protocol):
    """Protocol for processing specific notification types.

    Processors that need queue access should declare:
        queue: QueueService | None = None

    The NotificationHandler will inject the queue during registration
    for processors that have this attribute.
    """

    async def process(self, notification: Notification) -> dict[str, str]:
        """Process a notification and return response.

        Args:
            notification: The notification to process

        Returns:
            Dict containing response message and relevant data
        """
        ...
