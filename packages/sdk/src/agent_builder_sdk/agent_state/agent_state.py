# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from typing import Any, Dict


class IAgentState(ABC):
    pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to JSON-serializable dictionary."""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IAgentState":
        """Reconstruct state from dictionary."""
        pass
