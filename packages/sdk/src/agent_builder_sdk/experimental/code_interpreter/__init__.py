# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Sandboxed code execution via Bedrock AgentCore Code Interpreter.

The sandbox is a managed environment (Python 3.12 with pyarrow, pandas, numpy
preinstalled) — use it for computation over data. With the default interpreter it has
no AWS credentials and NO network egress: AWS APIs, customer buckets, and PyPI are
unreachable from inside. A custom interpreter selected with ``ATX_CODE_INTERPRETER_ID``
has the network access and the credentials it was created with. Data moves in with
``stage_file_to_sandbox`` and out through the tool's readFiles action; fetching from and
pushing to AWS stays in the agent container.

Sandbox sessions are billed until they end. ``stop_all_sessions`` stops them; it runs by
itself at a normal interpreter exit, but not when a signal ends the process.

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
    stop_all_sessions,
)

warnings.warn(
    "agent_builder_sdk.experimental.code_interpreter is an experimental feature. "
    "Code runs in a Bedrock AgentCore sandbox; move data in with stage_file_to_sandbox.",
    FutureWarning,
    stacklevel=2,
)

__all__ = ["create_code_interpreter_tool", "stop_all_sessions"]
