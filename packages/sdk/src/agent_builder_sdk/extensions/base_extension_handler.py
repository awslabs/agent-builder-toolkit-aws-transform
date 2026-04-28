from abc import ABC, abstractmethod
from typing import Any, Optional

from agent_builder_sdk.custom_types.extension_types import ExtensionResponse


class BaseExtensionHandler(ABC):
    """Abstract base class for all extension handler implementations."""

    def __init__(
        self,
        uri: str,
        required: bool = False,
        description: Optional[str] = None,
        params: Optional[dict] = None,
    ):
        self.uri = uri
        self.required = required
        self.description = description
        self.params = params

    @abstractmethod
    def should_process(self, *args: Any, **kwargs: Any) -> bool:
        """Determine if the extension handler should process the request."""
        pass

    @abstractmethod
    def process_request(self, *args: Any, **kwargs: Any) -> ExtensionResponse:
        """Process the request and return the response."""
        pass
