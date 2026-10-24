# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Types for multi-source conversation management."""

from enum import Enum
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from agent_builder_sdk.custom_types.orchestrator_agent_types import ConversationContext


class MessageSourceType(str, Enum):
    """Types of message sources."""

    USER = "USER"  # Human user interacting with the job/orchestrator
    SUBAGENT = "SUBAGENT"  # Specialized agent performing a specific task
    NOTIFICATION = "NOTIFICATION"  # System-generated message at job level


CURRENT_SOURCE_ID_KEY = "current_source_id"
CURRENT_SOURCE_TYPE_KEY = "current_source_type"
DEFAULT_SOURCE_ID = "global"


def classify_source(context: "ConversationContext") -> Tuple[str, "MessageSourceType"]:
    """Resolve (source_id, source_type) from a request context.

    Agent-type-neutral: it maps context fields to a source id + type, used both to key the
    streaming per-source agent pool and by the orchestrator's own turn processing.
    """
    if context.agent_instance_id and context.agent_instance_id != "ATX_CHAT":
        return context.agent_instance_id, MessageSourceType.SUBAGENT
    elif context.user_id:
        return context.user_id, MessageSourceType.USER
    else:
        return "SYSTEM", MessageSourceType.NOTIFICATION
