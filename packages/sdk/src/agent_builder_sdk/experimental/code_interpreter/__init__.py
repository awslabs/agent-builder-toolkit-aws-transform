# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Sandboxed code execution via Bedrock AgentCore Code Interpreter.

Wraps ``strands_tools.code_interpreter.AgentCoreCodeInterpreter``.
The sandbox is a managed environment (Python 3.12 with pyarrow, pandas, numpy
preinstalled) — use it for computation over data. It has no AWS credentials, and the
default interpreter has NO network egress: AWS APIs, customer buckets, and PyPI are
unreachable from inside. A custom interpreter selected with ``ATX_CODE_INTERPRETER_ID``
may have internet access. Data moves in with ``stage_file_to_sandbox`` and out through
the tool's readFiles action; fetching from and pushing to AWS stays in the agent
container (``execute_shell`` under connector credentials).

Needs the ``code-interpreter`` extra:
``pip install 'agent-builder-sdk-aws-transform[code-interpreter]'``.

Usage::

    from agent_builder_sdk.experimental.code_interpreter import (
        create_code_interpreter_tool,
    )

    agent = Agent(tools=create_code_interpreter_tool(region="us-west-2"))
"""

import warnings

from agent_builder_sdk.experimental.code_interpreter.code_interpreter_tool import (
    create_code_interpreter_tool,
)

warnings.warn(
    "agent_builder_sdk.experimental.code_interpreter is an experimental feature. "
    "Code runs in an AgentCore sandbox (network-isolated unless ATX_CODE_INTERPRETER_ID "
    "selects a custom interpreter); move data in with stage_file_to_sandbox.",
    FutureWarning,
    stacklevel=2,
)

__all__ = ["create_code_interpreter_tool"]
