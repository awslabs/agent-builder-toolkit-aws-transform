# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Experimental code execution support.

This module provides a local Python code execution tool for agents.
This is an experimental feature - the API may change.

Usage:
    from agent_builder_sdk.experimental.code_execution import python_repl

    agent = Agent(tools=[python_repl])

Or via agent factory:
    agent = create_default_async_orchestrator_with_subagent(
        enable_code_execution=True
    )

Future: AgentCore Code Interpreter integration for sandboxed execution.
"""

import warnings

from agent_builder_sdk.experimental.code_execution.code_execution_tool import python_repl

warnings.warn(
    "agent_builder_sdk.experimental.code_execution is an experimental feature. "
    "Code executes locally without sandboxing. Use with caution. "
    "AgentCore Code Interpreter integration planned for future release.",
    category=FutureWarning,
    stacklevel=2,
)

__all__ = ["python_repl"]
