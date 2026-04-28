"""Server models for agent runtime."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentRuntimeContext:
    """Agent runtime context containing workspace, job, and instance identifiers."""

    workspace_id: str
    job_id: str
    agent_instance_id: str
    agent_id: Optional[str] = None
    agent_version: Optional[str] = None
    initial_auth_token: Optional[str] = None
    tenant_account_id: Optional[str] = None
