"""Response types for A2A protocol"""

from dataclasses import dataclass
from typing import Optional, Union

from .common_types import A2AError, A2AMessage
from .task_types import A2ATask


@dataclass
class SendMessageOutput:
    """Agent Response for chat"""

    result: Optional[Union[A2AMessage, A2ATask]] = None
    error: Optional[A2AError] = None
