# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Sandboxed code execution via Bedrock AgentCore Code Interpreter.

Wraps ``strands_tools.code_interpreter.AgentCoreCodeInterpreter``.
The sandbox is a managed, network-isolated environment (Python 3.12 with pyarrow,
pandas, numpy preinstalled) — use it for computation over data. It has NO network
egress: AWS APIs, customer buckets, and PyPI are unreachable from inside. Data moves
in and out through the tool's writeFiles/readFiles actions; fetching from and pushing
to AWS stays in the agent container (``execute_shell`` under connector credentials).

Usage::

    from agent_builder_sdk.experimental.code_interpreter import (
        create_code_interpreter_tool,
    )

    agent = Agent(tools=[create_code_interpreter_tool(region="us-west-2")])
"""

import warnings

from agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool import (
    create_code_interpreter_tool,
)

warnings.warn(
    "agent_builder_sdk.experimental.code_interpreter is an experimental feature. "
    "Code runs in a network-isolated AgentCore sandbox; move data with writeFiles/readFiles.",
    FutureWarning,
    stacklevel=2,
)

__all__ = ["create_code_interpreter_tool"]
