# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Experimental shell execution support.

Provides a command-allowlisted shell execution tool for agents. This is an
experimental feature - the API may change.

Usage:
    from agent_builder_sdk.experimental.shell_execution import execute_shell

    agent = Agent(tools=[execute_shell])

Or via agent factory:
    agent = create_default_async_orchestrator_with_subagent(
        enable_shell=True
    )
"""

import warnings

from agent_builder_sdk.experimental.shell_execution.shell_execution_tool import execute_shell

warnings.warn(
    "agent_builder_sdk.experimental.shell_execution is an experimental feature. "
    "Shell runs in-container guarded only by a command allowlist. Use with caution.",
    category=FutureWarning,
    stacklevel=2,
)

__all__ = ["execute_shell"]
