# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""The Bedrock AgentCore Code Interpreter tools.

Two tools come out of :func:`create_code_interpreter_tool`:

- ``code_interpreter`` — runs code, shell commands and file operations (executeCode /
  executeCommand / readFiles / listFiles / removeFiles / writeFiles) in a managed Bedrock
  AgentCore sandbox with Python 3.12 and the data stack (pyarrow, pandas, numpy)
  preinstalled.
- ``stage_file_to_sandbox`` — copies a file from the agent container's filesystem
  into the sandbox. This exists because the sandbox of the default interpreter has no AWS
  credentials and NO network egress (no S3, no PyPI, no AWS APIs): data must be fetched in
  the agent container first and then staged across. Passing file bytes through the model's
  own tool arguments would put megabytes of base64 into the context window; this tool
  moves them process-to-sandbox directly.

Needs the ``code-interpreter`` extra:
``pip install 'agent-builder-sdk-aws-transform[code-interpreter]'``.
"""

import atexit
import logging
import os
import threading
import weakref
from typing import Any, Dict, Optional

from strands.tools import tool

from agent_builder_sdk.experimental.code_interpreter.agentcore_interpreter import (
    DEFAULT_INTERPRETER_ID,
    AgentCoreCodeInterpreter,
    CodeInterpreterInput,
)
from agent_builder_sdk.util.decorators import experimental

logger = logging.getLogger(__name__)

# writeFiles carries the payload through the InvokeCodeInterpreter request; keep well
# under the service request-size ceiling. Inspection workloads sample rather than
# shipping whole datasets across.
_MAX_STAGE_BYTES = 5 * 1024 * 1024

_DESCRIPTION = (
    "Run code, shell commands and file operations in an isolated Bedrock AgentCore Code "
    "Interpreter sandbox. Choose one action by its type: executeCode (Python by default, also "
    "JavaScript and TypeScript), executeCommand, readFiles, listFiles, removeFiles or writeFiles. "
    "A session keeps its files and its executeCode variables between calls. Leave session_name "
    "unset to use the default session; any other name selects a separate session, started on "
    "first use."
)

_ISOLATED_NOTE = (
    "\n\nIMPORTANT ENVIRONMENT NOTES:\n"
    "- The sandbox has NO network access and NO AWS credentials: no S3, no AWS APIs, no pip "
    "installs. Get data into the agent container first, then move it in with the "
    "stage_file_to_sandbox tool.\n"
    "- Preinstalled: Python 3.12 with pyarrow, pandas, numpy, boto3 (unusable "
    "offline), requests (unusable offline).\n"
    "- Results you need outside the sandbox: print them, or write files and use "
    "the readFiles action."
)

_CUSTOM_NOTE = (
    "\n\nIMPORTANT ENVIRONMENT NOTES:\n"
    "- This sandbox runs on a custom interpreter. Whether it can reach the internet (pip "
    "install, public endpoints) and whether it has AWS credentials depend on how that "
    "interpreter was set up, so do not assume either. If a network or AWS call fails in the "
    "sandbox, get the data into the agent container instead, then move it in with the "
    "stage_file_to_sandbox tool.\n"
    "- Preinstalled: Python 3.12 with pyarrow, pandas, numpy.\n"
    "- Results you need outside the sandbox: print them, or write files and use "
    "the readFiles action."
)

# The default is the managed interpreter, which is network-isolated. A deployment that
# needs more (for example PyPI access, through an interpreter created with PUBLIC network
# mode) sets this env var to the identifier of its own interpreter resource.
CODE_INTERPRETER_ID_ENV_VAR = "ATX_CODE_INTERPRETER_ID"

# Lifetime of each sandbox session. The service ends a session this long after it
# starts, regardless of activity, and its files and interpreter state go with it.
SESSION_TIMEOUT_ENV_VAR = "ATX_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS"
_DEFAULT_SESSION_TIMEOUT_SECONDS = 900
_MAX_SESSION_TIMEOUT_SECONDS = 28800  # service maximum (8 hours)

# The interpreters whose tools are still referenced. Weak, so the tools of an agent that
# was dropped do not keep its interpreter alive until the process exits.
_interpreters: "weakref.WeakSet[AgentCoreCodeInterpreter]" = weakref.WeakSet()
_interpreters_lock = threading.Lock()


@atexit.register
def stop_all_sessions() -> None:
    """Stop the sandbox sessions of every tool pair in this process that is still in use.

    A session that is not stopped keeps running, and is billed, until its timeout. This
    function runs by itself when the Python interpreter exits normally. It does not run when
    a signal ends the process, which is how a container runtime stops an agent (uvicorn
    re-raises SIGTERM after its graceful shutdown): call it from your own shutdown path to
    cover that. The sessions of a tool pair that was garbage-collected earlier are not
    stopped; they end at their timeout.

    It blocks for one StopCodeInterpreterSession request per session, so call it from a
    worker thread when an event loop is running.
    """
    with _interpreters_lock:
        interpreters = list(_interpreters)
    for interpreter in interpreters:
        interpreter.stop_all_sessions()


def _session_timeout_from_env() -> int:
    raw = os.getenv(SESSION_TIMEOUT_ENV_VAR)
    if not raw:
        return _DEFAULT_SESSION_TIMEOUT_SECONDS
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{SESSION_TIMEOUT_ENV_VAR} must be a whole number of seconds, got {raw!r}") from None


def create_code_interpreter_tool(
    region: Optional[str] = None,
    session_timeout_seconds: Optional[int] = None,
) -> list:
    """Build the sandbox tool pair for one agent.

    Returns ``[code_interpreter, stage_file_to_sandbox]`` sharing one interpreter
    instance, so files staged by one are visible to code run by the other (both
    default to the same sandbox session when ``session_name`` is omitted). Sessions
    belong to this pair, so two agents in one process never share a sandbox session,
    even when their models pick the same session name.

    The default interpreter (``aws.codeinterpreter.v1``) is network-isolated. Set
    ``ATX_CODE_INTERPRETER_ID`` to a custom interpreter's identifier to use it instead.
    Whether a custom interpreter has internet access depends on its network mode, so
    the tool description then tells the model not to assume either way.

    Sessions are stopped by :func:`stop_all_sessions`; see there for when it runs.

    Args:
        region: AWS region of the interpreter. Defaults to ``AWS_REGION``, then us-west-2.
        session_timeout_seconds: Lifetime of each sandbox session. Defaults to
            ``ATX_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS``, then 900 (15 minutes);
            capped at the service maximum of 28800 (8 hours). The service ends a session
            this long after it starts, regardless of activity, and its files go with it;
            the next call starts a new session, and its result says so, because files
            must be staged again.

    Raises:
        ValueError: ``ATX_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS`` is set and is not a
            whole number.
    """
    if session_timeout_seconds is None:
        session_timeout_seconds = _session_timeout_from_env()
    session_timeout_seconds = max(1, min(session_timeout_seconds, _MAX_SESSION_TIMEOUT_SECONDS))

    interpreter_id = os.getenv(CODE_INTERPRETER_ID_ENV_VAR) or DEFAULT_INTERPRETER_ID
    interpreter = AgentCoreCodeInterpreter(
        region=region or os.getenv("AWS_REGION") or "us-west-2",
        identifier=interpreter_id,
        session_timeout_seconds=session_timeout_seconds,
    )
    with _interpreters_lock:
        _interpreters.add(interpreter)

    note = _ISOLATED_NOTE if interpreter_id == DEFAULT_INTERPRETER_ID else _CUSTOM_NOTE

    @tool(description=_DESCRIPTION + note)
    @experimental("Runs code in a Bedrock AgentCore Code Interpreter sandbox.")
    def code_interpreter(code_interpreter_input: CodeInterpreterInput) -> Dict[str, Any]:
        # strands hands a model-typed parameter over as a plain dict.
        return interpreter.run(CodeInterpreterInput.model_validate(code_interpreter_input).action)

    @tool
    @experimental("Stages container files into the code-interpreter sandbox.")
    def stage_file_to_sandbox(
        local_path: str,
        sandbox_path: str,
        session_name: Optional[str] = None,
    ) -> str:
        """Copy a file from the agent container into the code-interpreter sandbox.

        Use this to hand data to sandbox code: get the file into the agent container
        first (for example under /tmp), then stage it here, then process it with the
        code_interpreter tool. Do not paste file contents through code_interpreter
        writeFiles for anything non-trivial — this tool moves the bytes directly. A
        sandbox session lasts a fixed time and is then replaced by a new, empty one;
        the result of the first call in the new session says so, and files must then
        be staged again.

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

        result = interpreter.invoke(session_name, "writeFiles", {"content": [{"path": sandbox_path, "blob": data}]})
        *notices, answer = [block["text"] for block in result["content"]]
        if result["status"] == "error":
            logger.warning("stage_file_to_sandbox failed: %s", answer)
            return " ".join([f"Error: staging failed: {answer}", *notices])
        logger.info("Staged %s (%d bytes) to sandbox:%s", local_path, size, sandbox_path)
        return " ".join(
            [
                f"Staged {local_path} ({size} bytes) to {sandbox_path} in the sandbox. "
                f"Code run via code_interpreter in the same session can now read it.",
                *notices,
            ]
        )

    return [code_interpreter, stage_file_to_sandbox]
