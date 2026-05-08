# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Request context for Orchestration Agent.

This module defines the RequestContext class for passing contextual information
during request processing between components.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestContext:
    """
    Context information for request processing.

    This class encapsulates contextual information that's passed along with requests,
    including identifiers for users and agent instances. Each orchestrator agent is
    bound to a single workspace+job combination, so those IDs are not needed in the context.
    The sender field identifies the source of the request (e.g., "subagent" or "chat").
    """

    # Source context id from chat agent
    context_id: Optional[str] = None

    # User identifier for multi-user support
    user_id: Optional[str] = None

    # Agent instance identifier for the current agent
    agent_instance_id: Optional[str] = None

    # Sender identity (e.g., "subagent" or "chat")
    sender: Optional[str] = None

    # Task ID when the current agent decides to start a task upfront or receives a send_message with a task_id
    task_id: Optional[str] = None
