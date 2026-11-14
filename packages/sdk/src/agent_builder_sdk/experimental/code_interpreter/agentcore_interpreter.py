# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Bedrock AgentCore Code Interpreter sessions for the ``code_interpreter`` tool.

``AgentCoreCodeInterpreter`` sends the tool's actions to the sandbox and owns the sessions they
run in. The action models follow those of the code-interpreter tool that strands-agents-tools
(Apache-2.0) shipped up to 0.8 and removed in 0.9.

Needs the ``code-interpreter`` extra:
``pip install 'agent-builder-sdk-aws-transform[code-interpreter]'``.
"""

import logging
import threading
import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, Field

try:
    from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter as CodeInterpreterClient
except ImportError as e:
    raise ImportError(
        "The code-interpreter tools need bedrock-agentcore. "
        "Install it with: pip install 'agent-builder-sdk-aws-transform[code-interpreter]'"
    ) from e

logger = logging.getLogger(__name__)

DEFAULT_INTERPRETER_ID = "aws.codeinterpreter.v1"

NEW_SESSION_NOTICE = (
    "Note: the sandbox session had ended, so this call ran in a new, empty session. Files and "
    "variables from the earlier session are gone; stage or create them again before you use them."
)


class LanguageType(str, Enum):
    """Languages the sandbox can execute."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


class FileContent(BaseModel):
    """A text file to write into the sandbox."""

    path: str = Field(description="Sandbox path of the file")
    text: str = Field(description="Text content of the file")


class _SessionAction(BaseModel):
    session_name: Optional[str] = Field(
        default=None,
        description="Sandbox session to run in. Leave unset to use the default session.",
    )

    def arguments(self) -> Dict[str, Any]:
        """The InvokeCodeInterpreter arguments of this action."""
        return self.model_dump(mode="json", by_alias=True, exclude={"type", "session_name"})


class ExecuteCodeAction(_SessionAction):
    """Run code in the session. Variables and imports stay available to later executeCode calls."""

    type: Literal["executeCode"]
    code: str = Field(description="Code to run")
    language: LanguageType = Field(default=LanguageType.PYTHON, description="Language of the code")
    clear_context: bool = Field(
        default=False,
        serialization_alias="clearContext",
        description="Discard the variables and imports of earlier executeCode calls first",
    )


class ExecuteCommandAction(_SessionAction):
    """Run a shell command in the sandbox."""

    type: Literal["executeCommand"]
    command: str = Field(description="Shell command to run")


class ReadFilesAction(_SessionAction):
    """Read files from the sandbox."""

    type: Literal["readFiles"]
    paths: List[str] = Field(description="Sandbox paths of the files to read")


class ListFilesAction(_SessionAction):
    """List the files in a sandbox directory."""

    type: Literal["listFiles"]
    path: str = Field(default=".", description="Sandbox directory to list")


class RemoveFilesAction(_SessionAction):
    """Delete files from the sandbox."""

    type: Literal["removeFiles"]
    paths: List[str] = Field(description="Sandbox paths of the files to delete")


class WriteFilesAction(_SessionAction):
    """Create or overwrite text files in the sandbox."""

    type: Literal["writeFiles"]
    content: List[FileContent] = Field(description="Files to write")


Action = Union[
    ExecuteCodeAction,
    ExecuteCommandAction,
    ReadFilesAction,
    ListFilesAction,
    RemoveFilesAction,
    WriteFilesAction,
]


class CodeInterpreterInput(BaseModel):
    """Input of the ``code_interpreter`` tool: one action, selected by its ``type``."""

    action: Action = Field(discriminator="type")


class AgentCoreCodeInterpreter:
    """Runs sandbox actions in Bedrock AgentCore Code Interpreter sessions.

    A session is known by its name, starts on the first call that names it and lives until the
    service ends it (``session_timeout_seconds`` after its start) or ``stop_all_sessions`` runs.
    Sessions belong to this instance: two instances that use the same name get two sandboxes.
    Calls from several threads are safe and share the session of a name.
    """

    def __init__(
        self,
        region: str,
        identifier: str = DEFAULT_INTERPRETER_ID,
        session_timeout_seconds: int = 900,
    ) -> None:
        """
        Args:
            region: AWS region of the interpreter.
            identifier: Interpreter to start sessions on.
            session_timeout_seconds: Lifetime of each session, 1 to 28800 (the service limits).
        """
        self.region = region
        self.identifier = identifier
        self.session_timeout_seconds = session_timeout_seconds
        self.default_session = f"session-{uuid.uuid4().hex[:12]}"
        self._sessions: Dict[str, CodeInterpreterClient] = {}
        self._lock = threading.Lock()

    def run(self, action: Action) -> Dict[str, Any]:
        """Run one ``code_interpreter`` action; see ``invoke`` for the result and the errors."""
        return self.invoke(action.session_name, action.type, action.arguments())

    def invoke(self, session_name: Optional[str], method: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a sandbox method in a session and return the outcome as a tool result.

        A call that fails because the service has ended the session runs once more, in a new
        session of the same name.

        Args:
            session_name: Session to run in; ``None`` selects the default session.
            method: InvokeCodeInterpreter method name, for example ``executeCode``.
            arguments: Arguments of the method.

        Returns:
            ``{"status": "success" | "error", "content": [{"text": ...}, ...]}``. The last content
            block is the sandbox's answer. ``NEW_SESSION_NOTICE`` comes before it when the call
            ran in a replacement session.

        Raises:
            ClientError: The session could not be started, or the call failed on a session that
                is still running.
            BotoCoreError: The request did not reach the service (credentials, endpoint, timeout).
        """
        name = session_name or self.default_session
        client = self._session(name)
        try:
            return _tool_result(client.invoke(method, arguments))
        except ClientError:
            if not self._forget_if_ended(name, client):
                raise
        logger.warning("Sandbox session %s has ended; running the call again in a new session", name)
        result = _tool_result(self._session(name).invoke(method, arguments))
        result["content"].insert(0, {"text": NEW_SESSION_NOTICE})
        return result

    def stop_all_sessions(self) -> None:
        """Stop every session this instance started, so none runs on until its timeout.

        A session that cannot be stopped is logged and skipped. The instance stays usable: a
        later call starts a new session. Call this when no action is in flight.
        """
        with self._lock:
            sessions, self._sessions = self._sessions, {}
        for name, client in sessions.items():
            try:
                client.stop()
            except (BotoCoreError, ClientError) as e:
                logger.warning("Could not stop sandbox session %s: %s", name, e)

    def _session(self, name: str) -> CodeInterpreterClient:
        # The lock covers the start as well as the lookup, so concurrent first calls on a name
        # share one session instead of starting one each.
        with self._lock:
            client = self._sessions.get(name)
            if client is None:
                client = CodeInterpreterClient(region=self.region)
                client.start(
                    identifier=self.identifier,
                    name=name,
                    session_timeout_seconds=self.session_timeout_seconds,
                )
                self._sessions[name] = client
                logger.info("Started sandbox session %s (%s)", name, client.session_id)
            return client

    def _forget_if_ended(self, name: str, used: CodeInterpreterClient) -> bool:
        """Whether a call that failed on ``used`` must run again in a new session.

        True when the service reports that the session has ended, and when a concurrent call
        that failed on the same session has already replaced it.
        """
        with self._lock:
            if self._sessions.get(name) is not used:
                return True
            if not _has_ended(used):
                return False
            del self._sessions[name]
            return True


def _has_ended(client: CodeInterpreterClient) -> bool:
    try:
        return client.get_session().get("status") != "READY"
    except ClientError as e:
        return e.response.get("Error", {}).get("Code") == "ResourceNotFoundException"


def _tool_result(response: Dict[str, Any]) -> Dict[str, Any]:
    # The service reports a failed action in the result event's isError, not as an exception.
    for event in response["stream"]:
        if "result" in event:
            result = event["result"]
            return {
                "status": "error" if result.get("isError") else "success",
                "content": [{"text": str(result.get("content"))}],
            }
    return {"status": "error", "content": [{"text": "The sandbox returned no result."}]}
