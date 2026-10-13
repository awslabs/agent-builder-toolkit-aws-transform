# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Wrapper for the Strands AgentCore Code Interpreter tool.

Two tools come out of :func:`create_code_interpreter_tool`:

- ``code_interpreter`` — the strands-provided sandbox tool (executeCode /
  executeCommand / writeFiles / readFiles / ...), running in a managed Bedrock
  AgentCore sandbox with Python 3.12 and the data stack (pyarrow, pandas, numpy)
  preinstalled.
- ``stage_file_to_sandbox`` — copies a file from the agent container's filesystem
  into the sandbox. This exists because the sandbox has no AWS credentials and, with
  the default interpreter, NO network egress (no S3, no PyPI, no AWS APIs): data must
  be fetched in the agent container first (e.g. ``execute_shell`` under connector
  credentials) and then staged across. Passing file bytes through the model's own
  tool arguments would put megabytes of base64 into the context window; this tool
  moves them process-to-sandbox directly.

Needs the ``code-interpreter`` extra:
``pip install 'agent-builder-sdk-aws-transform[code-interpreter]'``.
"""

import functools
import logging
import os
import threading
from copy import deepcopy
from typing import Any, Callable, Optional

from botocore.exceptions import ClientError
from strands.tools import tool

from agent_builder_sdk.util.decorators import experimental

try:
    from strands_tools.code_interpreter import AgentCoreCodeInterpreter
    from strands_tools.code_interpreter.models import FileContent, WriteFilesAction

    # Binary file content (FileContent.blob) arrived in strands-agents-tools 0.8.0.
    if "blob" not in FileContent.model_fields:
        raise ImportError("strands-agents-tools is older than 0.8.0")
except ImportError as e:
    raise ImportError(
        "The code-interpreter tools need strands-agents-tools>=0.8.0 and bedrock-agentcore. "
        "Install them with: pip install 'agent-builder-sdk-aws-transform[code-interpreter]'"
    ) from e

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

# Lifetime of each sandbox session. The service ends a session this long after it
# starts, regardless of activity, and its files and interpreter state go with it.
SESSION_TIMEOUT_ENV_VAR = "ATX_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS"
_DEFAULT_SESSION_TIMEOUT_SECONDS = 900
_MAX_SESSION_TIMEOUT_SECONDS = 28800  # service maximum (8 hours)

# The strands action methods that run against a session (all except initSession and
# listLocalSessions).
_SESSION_ACTIONS = (
    "execute_code",
    "execute_command",
    "read_files",
    "list_files",
    "remove_files",
    "write_files",
)


def _manage_sessions(interpreter: AgentCoreCodeInterpreter) -> Callable:
    """Close three gaps in strands' session handling, on this interpreter instance only.

    - Session names are process-wide: strands caches name -> session id at module
      level. A name the model picks is therefore prefixed with this instance's default
      session name, so two agents in one process that both pick "analysis" get
      separate sandboxes.
    - Session lookup-or-create is not thread-safe, and the orchestrator runs tool calls
      concurrently. One lock serializes it, so parallel first-use calls share one
      session instead of scattering staged files across several.
    - When a session's lifetime runs out, strands keeps using the cached session. A call
      that fails on a session the service reports as ended drops it and runs once more,
      which starts a new session. Parallel calls that failed on that same session run
      once more too, in the replacement the first one started.

    Returns the retry wrapper, for actions this module adds.
    """
    lock = threading.RLock()  # re-entrant: strands' _ensure_session calls init_session
    used = threading.local()  # .info: the session the call running on this thread resolved
    prefix = interpreter.default_session
    ensure_session = interpreter._ensure_session
    init_session = interpreter.init_session

    def scoped(name: Optional[str]) -> Optional[str]:
        return name if not name or name.startswith(prefix) else f"{prefix}-{name}"

    def locked_ensure_session(name: Optional[str]) -> Any:
        with lock:
            target, error = ensure_session(scoped(name))
            used.info = interpreter._sessions.get(target)
            return target, error

    def locked_init_session(action: Any) -> Any:
        with lock:
            return init_session(action.model_copy(update={"session_name": scoped(action.session_name)}))

    def session_ended(info: Any) -> bool:
        try:
            return info.client.get_session().get("status") != "READY"
        except ClientError as e:
            return e.response.get("Error", {}).get("Code") == "ResourceNotFoundException"

    def retry_on_ended_session(method: Callable) -> Callable:
        @functools.wraps(method)
        def wrapper(action: Any) -> Any:
            used.info = None
            try:
                return method(action)
            # KeyError: strands looks the session up again after resolving it, and a
            # concurrent call may have dropped it in between.
            except (ClientError, KeyError):
                name = scoped(action.session_name) or prefix
                with lock:
                    current = interpreter._sessions.get(name)
                    # If another call already dropped or replaced the session this call
                    # used, just run again; otherwise only if the service says it ended.
                    if current is used.info:
                        if current is None or not session_ended(current):
                            raise
                        del interpreter._sessions[name]
                logger.warning("Sandbox session %s has ended; retrying in a new session", name)
                return method(action)

        return wrapper

    interpreter._ensure_session = locked_ensure_session
    interpreter.init_session = locked_init_session
    for method_name in _SESSION_ACTIONS:
        setattr(interpreter, method_name, retry_on_ended_session(getattr(interpreter, method_name)))
    return retry_on_ended_session


def create_code_interpreter_tool(
    region: Optional[str] = None,
    session_timeout_seconds: Optional[int] = None,
) -> list:
    """Build the sandbox tool pair for one agent.

    Returns ``[code_interpreter, stage_file_to_sandbox]`` sharing one interpreter
    instance, so files staged by one are visible to code run by the other (both
    default to the same sandbox session when ``session_name`` is omitted). Session
    names the model picks are scoped to this pair, so two agents in one process never
    share a sandbox session.

    The default interpreter (``aws.codeinterpreter.v1``) is network-isolated. Set
    ``ATX_CODE_INTERPRETER_ID`` to a custom interpreter's identifier to use it instead;
    a custom interpreter may have internet access (e.g. PUBLIC network mode), and the
    tool description then tells the model it can pip install and reach public endpoints.

    Args:
        region: AWS region of the interpreter. Defaults to ``AWS_REGION``, then us-west-2.
        session_timeout_seconds: Lifetime of each sandbox session. Defaults to
            ``ATX_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS``, then 900 (15 minutes);
            capped at the service maximum of 28800 (8 hours). The service ends a session
            this long after it starts, regardless of activity, and its files go with it;
            the next call starts a new session, so files must be staged again.
    """
    if session_timeout_seconds is None:
        session_timeout_seconds = int(os.getenv(SESSION_TIMEOUT_ENV_VAR) or _DEFAULT_SESSION_TIMEOUT_SECONDS)
    session_timeout_seconds = max(1, min(session_timeout_seconds, _MAX_SESSION_TIMEOUT_SECONDS))

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

    retry_on_ended_session = _manage_sessions(interpreter)

    @retry_on_ended_session
    def write_files_checked(action: WriteFilesAction) -> Optional[str]:
        """Write the action's files; return the sandbox's error text, or None on success.

        strands' write_files reads isError from the top level of the response, where the
        service never sets it, so a rejected write passes as success. The flag is on each
        stream result.
        """
        name, error = interpreter._ensure_session(action.session_name)
        if error:
            return str(error.get("content"))
        content = [{"path": f.path, "blob": f.blob} for f in action.content]
        response = interpreter._sessions[name].client.invoke("writeFiles", {"content": content})
        for event in response.get("stream", []):
            if "result" in event:
                result = event["result"]
                return str(result.get("content")) if result.get("isError") else None
        return f"no result in the sandbox response: {response}"

    @tool
    @experimental("Stages container files into the code-interpreter sandbox.")
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
        non-trivial — this tool moves the bytes directly. A sandbox session lasts a
        fixed time and is then replaced by a new, empty one, so stage files again if
        sandbox code can no longer find them.

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
        error = write_files_checked(action)
        if error is not None:
            logger.warning("stage_file_to_sandbox failed: %s", error)
            return f"Error: staging failed: {error}"
        logger.info("Staged %s (%d bytes) to sandbox:%s", local_path, size, sandbox_path)
        return (
            f"Staged {local_path} ({size} bytes) to {sandbox_path} in the sandbox. "
            f"Code run via code_interpreter in the same session can now read it."
        )

    return [code_interpreter_tool, stage_file_to_sandbox]
