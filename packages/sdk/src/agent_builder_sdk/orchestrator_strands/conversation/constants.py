# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Types for multi-source conversation management."""

from enum import Enum


class MessageSourceType(str, Enum):
    """Types of message sources."""

    USER = "USER"  # Human user interacting with the job/orchestrator
    SUBAGENT = "SUBAGENT"  # Specialized agent performing a specific task
    NOTIFICATION = "NOTIFICATION"  # System-generated message at job level


CURRENT_SOURCE_ID_KEY = "current_source_id"
CURRENT_SOURCE_TYPE_KEY = "current_source_type"
DEFAULT_SOURCE_ID = "global"
