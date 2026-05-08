# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Message processor interface for handling communication between agents.

This module defines the abstract interface for message processing,
allowing different implementations for various communication protocols.

"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class RequestHandler(ABC):
    """
    Abstract base class for request handling.

    This class defines the interface for processing incoming requests and storing responses.
    It handles the complete request lifecycle: receiving requests from various sources
    (queues, HTTP endpoints, etc.), processing them, and storing the results for retrieval.
    """

    @abstractmethod
    async def receive_request(self) -> Optional[Dict[str, Any]]:
        """
        Receive a request from a queue or external source.

        This method retrieves the next available request for processing.
        It should handle timeouts gracefully and return None when no requests
        are available or when the handler should stop processing.

        Returns:
            Dict containing the request data and context, or None if no request available
        """
        pass

    @abstractmethod
    async def store_response(self, response: str, recipient_id: Optional[str] = None) -> bool:
        """
        Store the response for the current or specified request.

        This method persists the processed response so it can be retrieved later.
        It should handle the complete response lifecycle including status updates
        and error handling.

        Args:
            response: The response content to store
            recipient_id: Optional identifier of the request (if None, uses current request)

        Returns:
            True if response was stored successfully, False otherwise
        """
        pass
