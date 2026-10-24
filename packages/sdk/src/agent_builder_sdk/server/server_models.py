# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Server models for agent runtime."""

from dataclasses import dataclass
from typing import Optional

from agent_builder_sdk.locale_utils import get_locale_instruction


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
    locale: Optional[str] = None

    def get_locale_instruction(self) -> str:
        """Return a system prompt instruction for the agent's current locale."""
        return get_locale_instruction(self.locale)
