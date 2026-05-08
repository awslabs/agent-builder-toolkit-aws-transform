"""
Base helper class for agentic API operations.
"""

import logging
from abc import ABC
from typing import Any

import agent_builder_types.type_defs as abt

from agent_builder_sdk.env_var import retrieve_auth_token

logger = logging.getLogger(__name__)


class AgenticApiHelper(ABC):
    """Base class for agentic API helpers."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.workspace_id = self._check_arg(kwargs, "workspace_id", str)
        self.job_id = self._check_arg(kwargs, "job_id", str)
        self.agent_instance_id = self._check_arg(kwargs, "agent_instance_id", str)
        self.client = kwargs["client"]

    def _check_arg(self, kwargs: dict, arg_name: str, expected_type: type) -> Any:
        """Validate required arguments."""
        arg_value = kwargs.get(arg_name)
        if arg_value is None:
            raise ValueError(f"{arg_name} is a required argument")
        if not isinstance(arg_value, expected_type):
            raise TypeError(f"Argument '{arg_name}' must be of type {expected_type.__name__}")
        return arg_value

    def _create_request_context(self) -> abt.RequestContextTypeDef:
        """Build request context for API calls."""
        return {
            "jobMetadata": {"jobId": self.job_id, "workspaceId": self.workspace_id},
            "agentInstanceId": self.agent_instance_id,
            "authorizationToken": retrieve_auth_token(),
        }

    def _inject_request_context(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Build request context for API calls."""
        return {**request_data, "requestContext": self._create_request_context()}


def get_agent_registry(**kwargs):
    """Factory function to create AgentRegistry instance."""
    from agent_builder_sdk.agentic_framework.agent_registry import AgentRegistry

    return AgentRegistry(**kwargs)
