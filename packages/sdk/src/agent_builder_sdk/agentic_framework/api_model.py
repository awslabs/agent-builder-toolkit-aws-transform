"""
API models for agentic framework - minimal implementation for checkpointing.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

import mypy_boto3_elasticgumbyagenticservice.type_defs as eg

T = TypeVar("T", bound=Mapping)


# https://code.amazon.com/packages/ElasticGumbyArtifactStoreServiceModel/blobs/b4476a2b50362976768f877e77d7994675d7ed97/--/model/dataTypes/common.smithy#L67
class CategoryType(str, Enum):
    """Artifact category types."""

    AGENT_INPUT = "AGENT_INPUT"
    AGENT_OUTPUT = "AGENT_OUTPUT"
    CUSTOMER_INPUT = "CUSTOMER_INPUT"
    CUSTOMER_OUTPUT = "CUSTOMER_OUTPUT"
    HITL_FROM_AGENT = "HITL_FROM_AGENT"
    HITL_FROM_USER = "HITL_FROM_USER"
    STATE = "STATE"
    PLAN_STEP_OUTPUT = "PLAN_STEP_OUTPUT"
    PLAN_STEP_SUMMARY = "PLAN_STEP_SUMMARY"
    INTERNAL = "INTERNAL"


class FileType(str, Enum):
    """File types for artifacts."""

    JSON = "JSON"
    ZIP = "ZIP"


class Visibility(str, Enum):
    """Artifact visibility levels."""

    INTERNAL = "INTERNAL"


class ApiShapeMixin(Generic[T]):
    """Base mixin for API request/response shapes."""

    def to_dict(self) -> T:
        """
        Converting dataclass to AgenticAPI requests expected format.
        """
        raise NotImplementedError("Perhaps you forgot to implement this method?")


@dataclass(frozen=True)
class AgenticApiRequestContext(ApiShapeMixin[eg.RequestContextTypeDef]):
    """
    Request context for Elastic Gumby Agentic API calls.
    Contains job metadata and agent identification information.
    """

    job_id: str
    workspace_id: str
    agent_instance_id: str
    authorization_token: str = field(repr=False)

    def to_dict(self) -> eg.RequestContextTypeDef:
        """
        Convert to dictionary format expected by the API.
        """
        return {
            "jobMetadata": {"jobId": self.job_id, "workspaceId": self.workspace_id},
            "agentInstanceId": self.agent_instance_id,
            "authorizationToken": self.authorization_token,
        }
