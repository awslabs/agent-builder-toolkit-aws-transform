# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Wrapper for the Strands AgentCore Code Interpreter tool.

Two tools come out of :func:`create_code_interpreter_tool`:

- ``code_interpreter`` — the strands-provided sandbox tool (executeCode /
  executeCommand / writeFiles / readFiles / ...), running in a managed Bedrock
  AgentCore sandbox with Python 3.12 and the data stack (pyarrow, pandas, numpy)
  preinstalled.
- ``stage_file_to_sandbox`` — copies a file from the agent container's filesystem
  into the sandbox. This exists because the sandbox has NO network egress (no S3,
  no PyPI, no AWS APIs): data must be fetched in the agent container first (e.g.
  ``execute_shell`` under connector credentials) and then staged across. Passing
  file bytes through the model's own tool arguments would put megabytes of base64
  into the context window; this tool moves them process-to-sandbox directly.
"""

import logging
import os
from copy import deepcopy
from typing import Any, Optional

from strands.tools import tool
from strands_tools.code_interpreter import AgentCoreCodeInterpreter
from strands_tools.code_interpreter.models import FileContent, WriteFilesAction

from agent_builder_sdk.util.decorators import experimental

logger = logging.getLogger(__name__)

# writeFiles carries the payload through the InvokeCodeInterpreter request; keep well
# under the service request-size ceiling. Inspection workloads sample rather than
# shipping whole datasets across.
_MAX_STAGE_BYTES = 5 * 1024 * 1024

_SANDBOX_NOTE = (
    "\n\nIMPORTANT ENVIRONMENT NOTES:\n"
    "- The sandbox has NO network access: no S3, no AWS APIs, no pip installs. "
    "Fetch data in the agent container first (execute_shell under connector "
    "credentials), then move it in with the stage_file_to_sandbox tool.\n"
    "- Preinstalled: Python 3.12 with pyarrow, pandas, numpy, boto3 (unusable "
    "offline), requests (unusable offline).\n"
    "- Results you need outside the sandbox: print them, or write files and use "
    "the readFiles action."
)

_PUBLIC_NOTE = (
    "\n\nIMPORTANT ENVIRONMENT NOTES:\n"
    "- The sandbox HAS public internet access: you can pip install packages a "
    "skill needs (e.g. pip install -r requirements.txt) and reach public "
    "endpoints. It has NO AWS credentials, so fetch account data in the agent "
    "container first (execute_shell under connector credentials), then move it "
    "in with the stage_file_to_sandbox tool.\n"
    "- Preinstalled: Python 3.12 with pyarrow, pandas, numpy.\n"
    "- Results you need outside the sandbox: print them, or write files and use "
    "the readFiles action."
)


# A custom interpreter resource (CreateCodeInterpreter) can be configured with
# PUBLIC network mode, which restores PyPI/internet access inside sessions for
# skills whose requirements go beyond the preinstalled set. Deployments opt in by
# setting this env var to the custom interpreter's identifier; the default is the
# managed public interpreter, which is network-isolated (Sandbox mode).
CODE_INTERPRETER_ID_ENV_VAR = "ATX_CODE_INTERPRETER_ID"
_DEFAULT_INTERPRETER_ID = "aws.codeinterpreter.v1"


def create_code_interpreter_tool(
    region: Optional[str] = None,
    session_timeout_seconds: int = 900,
) -> list:
    """Build the sandbox tool pair for one agent.

    Returns ``[code_interpreter, stage_file_to_sandbox]`` sharing one interpreter
    instance, so files staged by one are visible to code run by the other (both
    default to the same sandbox session when ``session_name`` is omitted).
    """
    interpreter_id = os.getenv(CODE_INTERPRETER_ID_ENV_VAR) or _DEFAULT_INTERPRETER_ID
    interpreter = AgentCoreCodeInterpreter(
        region=region or os.getenv("AWS_REGION") or "us-west-2",
        identifier=interpreter_id,
        session_timeout_seconds=session_timeout_seconds,
    )
    # strands hands every AgentCoreCodeInterpreter instance the SAME class-level
    # tool_spec dict, so appending our note in place would mutate every other
    # agent's tool description too (double note under concurrent construction,
    # cross-instance rewrite even when serialized). Give this instance its own
    # deep-copied spec before appending, so the note is per-agent and idempotent.
    code_interpreter_tool = interpreter.code_interpreter
    code_interpreter_tool._tool_spec = deepcopy(code_interpreter_tool._tool_spec)
    # The default interpreter is network-isolated; a custom one is provisioned PUBLIC.
    is_isolated = interpreter_id == _DEFAULT_INTERPRETER_ID
    code_interpreter_tool.tool_spec["description"] += _SANDBOX_NOTE if is_isolated else _PUBLIC_NOTE

    @tool
    @experimental("Stages container files into the network-isolated sandbox.")
    def stage_file_to_sandbox(
        local_path: str,
        sandbox_path: str,
        session_name: Optional[str] = None,
    ) -> str:
        """Copy a file from the agent container into the code-interpreter sandbox.

        Use this to hand data to sandbox code: download it first in the agent
        container (e.g. execute_shell with connector credentials writing to /tmp),
        then stage it here, then process it with the code_interpreter tool. Do not
        paste file contents through code_interpreter writeFiles for anything
        non-trivial — this tool moves the bytes directly.

        Args:
            local_path: Path of the file inside the agent container (e.g. /tmp/data.parquet).
            sandbox_path: Destination path inside the sandbox (e.g. data/data.parquet).
            session_name: Sandbox session to stage into. Leave unset to use the same
                default session the code_interpreter tool uses.

        Returns:
            A confirmation with the sandbox path, or an error description.
        """
        if not os.path.isfile(local_path):
            return f"Error: no such file in the agent container: {local_path}"
        size = os.path.getsize(local_path)
        if size > _MAX_STAGE_BYTES:
            return (
                f"Error: {local_path} is {size} bytes; the sandbox transfer limit is "
                f"{_MAX_STAGE_BYTES}. Sample or split the data first (e.g. copy only "
                f"the ranges you need), then stage the smaller file."
            )
        with open(local_path, "rb") as f:
            data = f.read()

        action = WriteFilesAction(
            type="writeFiles",
            session_name=session_name,
            content=[FileContent(path=sandbox_path, blob=data)],
        )
        result: dict[str, Any] = interpreter.write_files(action)
        if result.get("status") != "success":
            logger.warning("stage_file_to_sandbox failed: %s", result)
            return f"Error: staging failed: {result.get('content')}"
        logger.info("Staged %s (%d bytes) to sandbox:%s", local_path, size, sandbox_path)
        return (
            f"Staged {local_path} ({size} bytes) to {sandbox_path} in the sandbox. "
            f"Code run via code_interpreter in the same session can now read it."
        )

    return [code_interpreter_tool, stage_file_to_sandbox]
