# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Custom message class for conversation storage."""

import base64
import inspect
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from strands.types.content import Message


def encode_bytes_values(obj: Any) -> Any:
    """Recursively encode any bytes values in an object to base64.

    Handles dictionaries, lists, and nested structures.
    """
    if isinstance(obj, bytes):
        return {"__bytes_encoded__": True, "data": base64.b64encode(obj).decode()}
    elif isinstance(obj, dict):
        return {k: encode_bytes_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [encode_bytes_values(item) for item in obj]
    else:
        return obj


def decode_bytes_values(obj: Any) -> Any:
    """Recursively decode any base64-encoded bytes values in an object.

    Handles dictionaries, lists, and nested structures.
    """
    if isinstance(obj, dict):
        if obj.get("__bytes_encoded__") is True and "data" in obj:
            return base64.b64decode(obj["data"])
        return {k: decode_bytes_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decode_bytes_values(item) for item in obj]
    else:
        return obj


@dataclass
class ConversationMessage:
    """
    Custom message class for conversation storage.

    This class wraps the Strands Message class and adds additional metadata
    needed for conversation management, such as timestamps for ordering.

    Attributes:
        message: Original message content
        created_at: ISO format timestamp for when this message was created
    """

    message: Message
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_message(cls, message: Message) -> "ConversationMessage":
        """
        Create a ConversationMessage from a Strands Message.

        Args:
            message: The Strands Message to wrap

        Returns:
            A new ConversationMessage instance
        """
        return cls(message=message, created_at=datetime.now(timezone.utc).isoformat())

    def to_message(self) -> Message:
        """
        Get the original Strands Message.

        Returns:
            The original Strands Message
        """
        return self.message

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMessage":
        """
        Create a ConversationMessage from a dictionary.

        Args:
            data: Dictionary representation of a ConversationMessage

        Returns:
            A new ConversationMessage instance
        """
        # Extract only the parameters that match our class signature
        extracted_params = {k: v for k, v in data.items() if k in inspect.signature(cls).parameters}

        # Decode any bytes values
        decoded_params = decode_bytes_values(extracted_params)

        return cls(**decoded_params)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a dictionary for serialization.

        Returns:
            A dictionary representation of this message
        """
        # Convert to dictionary and encode any bytes values
        return encode_bytes_values(asdict(self))
