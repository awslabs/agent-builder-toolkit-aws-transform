# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Acknowledgment extension for agent message processing.

Provides automatic acknowledgment functionality for incoming messages from specific senders,
enabling immediate response while processing continues asynchronously in the background.
"""

from typing import Optional

from agent_builder_sdk.custom_types.extension_types import ExtensionResponse
from agent_builder_sdk.extensions.base_extension_handler import BaseExtensionHandler

ACK_URI = "https://aws.com/transform/ext/acknowledgment/v1"


class AcknowledgmentHandler(BaseExtensionHandler):
    """
    Extension handler that provides automatic acknowledgment for incoming messages.

    Sends immediate acknowledgment responses to specific senders (e.g., ATX_CHAT)
    while allowing the actual message processing to continue asynchronously.
    This improves user experience by providing instant feedback that the request
    was received and is being processed.
    """

    def __init__(
        self,
        required: bool = False,
        description: Optional[str] = None,
        params: Optional[dict] = None,
    ):
        """
        Initialize the Acknowledgment Handler.

        Args:
            required (bool): Whether the extension is required.
            description (str): The description of the extension.
            params (dict): The parameters of the extension.
        """
        super().__init__(uri=ACK_URI, required=required, description=description, params=params)

    def should_process(self, **kwargs) -> bool:
        sender = kwargs.get("sender", "")
        return sender == "ATX_CHAT"

    def process_request(self, **kwargs) -> ExtensionResponse:
        """
        Create a structured acknowledgment to be sent back to the requester
        """
        return ExtensionResponse(
            message="I'm working on your request and will get back to you shortly.",
            metadata={self.uri: True},
            extensions=[self.uri],
        )
