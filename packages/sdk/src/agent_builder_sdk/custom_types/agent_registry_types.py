# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Type definitions for agent registry operations.

This module contains types used for interacting with the ATX platform's agent registry.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentType(Enum):
    """Type of the agent."""

    ORCHESTRATOR_AGENT = "ORCHESTRATOR_AGENT"
    SUB_AGENT = "SUB_AGENT"


class AgentVisibility(Enum):
    """Agent visibility status configured by the partner."""

    PUBLIC = "PUBLIC"
    RESTRICTED = "RESTRICTED"


class VersionStatus(Enum):
    """Status of an agent version."""

    CREATED = "CREATED"
    IN_VERIFICATION = "IN_VERIFICATION"
    ACTIVE = "ACTIVE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class MonitoringType(Enum):
    """Monitoring type for agents."""

    HEARTBEAT = "HEARTBEAT"
    HEALTHCHECK = "HEALTHCHECK"


class NotificationStatus(Enum):
    """Notification status for agents."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


@dataclass
class AgentExtension:
    """Agent extension definition."""

    name: str
    version: str


@dataclass
class AgentSkill:
    """Agent skill - capability units that the agent can execute."""

    id: str
    name: str
    description: str
    tags: List[str]
    examples: Optional[List[str]] = None
    input_modes: Optional[List[str]] = None
    output_modes: Optional[List[str]] = None


@dataclass
class AgentCapabilities:
    """Agent capability definitions."""

    extensions: Optional[List[AgentExtension]] = None
    push_notifications: Optional[bool] = None
    state_transition_history: Optional[bool] = None
    streaming: Optional[bool] = None


@dataclass
class AgentProvider:
    """Agent service provider."""

    organization: str
    url: str


# TODO: actual definition
@dataclass
class SecurityScheme:
    """Security scheme definition."""

    pass


@dataclass
class AgentCard:
    """Agent card - contains key information about the agent."""

    name: str
    description: str
    version: str
    url: str
    skills: List[AgentSkill]
    capabilities: AgentCapabilities
    protocol_version: Optional[str] = "0.2.5"
    default_input_modes: Optional[List[str]] = None
    default_output_modes: Optional[List[str]] = None
    provider: Optional[AgentProvider] = None
    security: Optional[List[Dict[str, List[str]]]] = None
    security_schemes: Optional[Dict[str, SecurityScheme]] = None

    def __post_init__(self):
        if self.skills is None:
            self.skills = []
        if self.default_input_modes is None:
            self.default_input_modes = []
        if self.default_output_modes is None:
            self.default_output_modes = []


@dataclass
class AgentMetadata:
    """Metadata for an agent."""

    type: AgentType
    description: str
    owner_name: str
    owner_account_id: str
    owner_contact_info: str


# TODO: actual definition
@dataclass
class ComputeConfiguration:
    """Compute configuration for an agent."""

    pass


# TODO: actual definition
@dataclass
class LegacyAgentResiliencyConfiguration:
    """Legacy agent resiliency configuration."""

    pass


# TODO: the following are not actually optional - computeConfiguration, inputPayloadSchema, outputPayloadSchema
@dataclass
class AgentConfiguration:
    """Configuration for an agent."""

    short_description: str
    status: VersionStatus
    agent_card: AgentCard
    monitoring_type: MonitoringType
    notifications_enabled: NotificationStatus
    compute_configuration: Optional[ComputeConfiguration] = None
    input_payload_schema: Optional[Dict[str, Any]] = None
    output_payload_schema: Optional[Dict[str, Any]] = None
    objective_negotiation_prompt: Optional[str] = None
    status_msg: Optional[str] = None
    agent_resiliency_configuration: Optional[LegacyAgentResiliencyConfiguration] = None


@dataclass
class GetAgentVersionOutput:
    """Output structure for getting agent version."""

    version: str
    metadata: AgentMetadata
    visibility: AgentVisibility
    configuration: AgentConfiguration
    status: VersionStatus
    status_message: Optional[str] = None
