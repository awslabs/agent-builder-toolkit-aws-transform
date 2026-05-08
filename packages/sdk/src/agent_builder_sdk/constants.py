# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Application-wide constants for the AWS Transform Platform Base Agent.
"""

# Tool filtering constants
DEFAULT_SUBAGENT_EXCLUDED_TOOLS = [
    # Agent tools
    "invoke_agent",
    # Job tools
    "put_job_plan",
    "update_job_status",
    "delete_job_plan_step",
]
