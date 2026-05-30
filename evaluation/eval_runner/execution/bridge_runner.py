# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge runner wrapping ACPClient for eval scenario execution.

This module provides a Python wrapper around the ACPClient class from
acp_bridge.py. Uses ACPClient directly in-process for clean ACP
communication with agent-cli.

Architecture::

    BridgeRunner
        │
        ├── start()   → ACPClient.start() → agent-cli acp (subprocess)
        ├── prompt()  → ACPClient.prompt() → JSON-RPC over stdin/stdout
        ├── approve() → ACPClient.send_approval()
        └── destroy() → ACPClient.kill()

Usage::

    bridge = BridgeRunner(session_name="eval-test")
    bridge.start()
    response = bridge.prompt(agent="kiro_default", text="Say hello")
    print(response.text)  # "Hello!"
    print(response.usage)  # {"inputTokens": 100, "outputTokens": 50, ...}
    bridge.destroy()
"""

# mypy: disable-error-code="no-any-return,misc,arg-type,attr-defined"

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .acp_bridge import ACPClient

logger = logging.getLogger(__name__)


class BridgeResponseStatus(str, Enum):
    """Status of a bridge prompt or approval response.

    Values:
        SUCCESS: The prompt completed successfully with a text response.
        APPROVAL_NEEDED: The agent requested tool approval. Use ``approve()``
            to continue.
        TIMEOUT: The prompt exceeded the timeout limit.
        FAILED: The prompt failed due to an error (process crash, etc.).
        ERROR: The bridge daemon returned an error (not running, etc.).
    """

    SUCCESS = "SUCCESS"
    APPROVAL_NEEDED = "APPROVAL_NEEDED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    ERROR = "ERROR"


@dataclass
class BridgeResponse:
    """Response from a bridge prompt or approval call.

    Attributes:
        status: The outcome of the call (SUCCESS, APPROVAL_NEEDED, etc.).
        text: The agent's text response. Empty for non-SUCCESS statuses.
        tool_call_id: The tool call ID requiring approval (only when
            status is APPROVAL_NEEDED).
        tool_name: Human-readable name of the tool requesting approval.
        approval_options: Available approval options (e.g., ["allow_once",
            "allow_always", "reject_once"]).
        error: Error message if status is FAILED/TIMEOUT/ERROR.
        raw_results: The full ``results`` list from the bridge response,
            for detailed inspection.
        log_path: Path to the per-prompt log file written by the bridge.
        usage: Token usage from the ACP PromptResponse. Contains keys like
            ``inputTokens``, ``outputTokens``, ``totalTokens``,
            ``cachedReadTokens``. None if not available.
        tool_calls: List of tool call events captured during the prompt.
    """

    status: BridgeResponseStatus
    text: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    approval_options: list[str] = field(default_factory=list)
    error: str | None = None
    raw_results: list[dict[str, Any]] = field(default_factory=list)
    log_path: str | None = None
    usage: dict[str, Any] | None = None
    tool_calls: list[dict[str, str]] = field(default_factory=list)


class BridgeRunner:
    """Wraps ACPClient for eval scenario execution.

    Uses ACPClient directly in-process (no daemon/socket layer) to avoid
    MCP server initialization failures caused by the daemon subprocess
    environment.

    Attributes:
        session_name: Unique name for this bridge session.
        cwd: Working directory for the agent-cli acp session.
    """

    def __init__(
        self,
        session_name: str,
        cwd: str | None = None,
        verbose: bool = False,
        has_mcp: bool = False,
        resource_logger: Any | None = None,
        binary: str = "agent-cli",
    ) -> None:
        self.session_name = session_name
        self.cwd = cwd or "/tmp"
        self.verbose = verbose
        self.has_mcp = has_mcp
        self.resource_logger = resource_logger
        self.binary = binary  # ACP driver binary (e.g. "agent-cli", "kiro-cli")
        self._client: ACPClient | None = None
        self._started = False

    @property
    def session_id(self) -> str | None:
        """Return the agent-cli ACP session ID, or None if not started."""
        return self._client.session_id if self._client else None

    def start(self, agent: str = "kiro_default") -> None:
        """Start agent-cli ACP session directly via ACPClient.

        Creates an ACPClient instance with the target agent and starts it.
        No daemon or socket — the ACP process runs as a direct child.

        Args:
            agent: Name of the agent-cli agent to use (e.g., "my-agent-under-test").

        Raises:
            RuntimeError: If the ACP session fails to start.
        """
        log_path = os.path.join(
            self.cwd,
            f"{self.session_name}_{time.strftime('%Y%m%d_%H%M%S')}_acp.log",
        )
        self._client = ACPClient(
            agent,
            log_path,
            cwd=self.cwd,
            verbose=self.verbose,
            has_mcp=self.has_mcp,
            binary=self.binary,
        )
        logger.info(
            f"  bridge >> starting {self.session_name} agent={agent} (waiting for MCP init...)"
        )
        self._client.start()
        logger.info(f"  bridge >> ready {self.session_name} cwd={self.cwd}")
        if self._client.session_id:
            logger.info(
                f"  bridge >> session {self._client.session_id}"
                f" mode={self._client.current_mode}"
            )
        self._started = True

    def prompt(
        self,
        agent: str,
        text: str,
        timeout: int = 120,
        auto_approve: bool = True,
        max_approvals: int = 20,
    ) -> BridgeResponse:
        """Send a prompt to agent-cli via ACPClient and collect the response.

        Args:
            agent: Name of the agent-cli agent (used for logging, not routing).
            text: The prompt text to send.
            timeout: Per-prompt timeout in seconds. Defaults to 120.
            auto_approve: If True, automatically approves tool calls with
                ``allow_once``. Defaults to True for eval scenarios.
            max_approvals: Maximum number of auto-approvals per prompt to
                prevent infinite loops. Defaults to 20.

        Returns:
            A ``BridgeResponse`` with the agent's text response.
        """
        if not self._client:
            return BridgeResponse(
                status=BridgeResponseStatus.ERROR,
                error="Bridge not started",
            )

        tool_calls: list[dict[str, str]] = []
        agent_text_buf: list[str] = []

        def _flush_agent_text() -> None:
            """Log accumulated agent text and clear the buffer."""
            if agent_text_buf:
                text = "".join(agent_text_buf).strip()
                if text:
                    logger.info(f"  agent[text] >> {text}")
                agent_text_buf.clear()

        def on_event(event: dict) -> None:
            if event.get("type") == "agent_text":
                agent_text_buf.append(event.get("text", ""))
                return
            # Flush any accumulated agent text before logging the tool event
            _flush_agent_text()
            tool = event.get("tool", "")
            kind = event.get("kind", "")
            status = event.get("status", "")
            tool_calls.append({"tool": tool, "kind": kind, "status": status})
            logger.info(f"  agent[tool] >> {tool} ({kind}) → {status}")
            # Optional resource logging (e.g., workspace/job IDs)
            if self.resource_logger and event.get("raw_output"):
                try:
                    self.resource_logger(tool, event.get("raw_output"))
                except Exception:
                    logger.debug("resource_logger raised an exception", exc_info=True)

        status, data = self._client.prompt(text, timeout, on_event=on_event)
        _flush_agent_text()

        response = self._make_response(status, data, tool_calls)

        # Auto-approve loop with upper bound to prevent infinite loops
        initial_log_path = self._client.log_path
        approvals_count = 0
        while auto_approve and response.status == BridgeResponseStatus.APPROVAL_NEEDED:
            approvals_count += 1
            if approvals_count > max_approvals:
                logger.error(f"Exceeded max approvals ({max_approvals}) for prompt")
                return BridgeResponse(
                    status=BridgeResponseStatus.ERROR,
                    error=f"Exceeded max approvals ({max_approvals})",
                    tool_calls=tool_calls,
                    log_path=initial_log_path,
                )
            logger.info(f"  human[approve] >> {response.tool_name}")
            approve_status, approve_data = self._client.send_approval(
                "allow_once", timeout=timeout, on_event=on_event
            )
            response = self._make_response(approve_status, approve_data, tool_calls)
            if not response.log_path:
                response.log_path = initial_log_path
        if not response.log_path:
            response.log_path = self._client.log_path

        return response

    def approve(
        self,
        option: str = "allow_once",
    ) -> BridgeResponse:
        """Send a tool approval decision and resume the prompt."""
        if not self._client:
            return BridgeResponse(
                status=BridgeResponseStatus.ERROR,
                error="Bridge not started",
            )

        status, data = self._client.send_approval(option)
        return self._make_response(status, data, [])

    def dump_mcp_logs(self) -> str | None:
        """Send /logdump --mcp to capture MCP server logs before destroying.

        Returns the log dump text, or None if it failed.
        """
        if not self._client or not self._started:
            return None
        try:
            status, data = self._client.prompt("/logdump --mcp", timeout=10)
            if status == "SUCCESS":
                text = data.get("response", "")
                if text:
                    logger.info(f"  mcp   >> logdump: {text[:200]}")
                return text
        except Exception as e:
            logger.debug(f"Failed to dump MCP logs: {e}")
        return None

    def destroy(self) -> None:
        """Kill the agent-cli ACP process.

        Always call this at the end of a scenario, even on failure.
        """
        if not self._started or not self._client:
            return

        self._client.kill()
        logger.info(f"Bridge destroyed: {self.session_name}")
        self._started = False
        self._client = None

    def _make_response(
        self,
        status: str,
        data: dict[str, Any],
        tool_calls: list[dict[str, str]],
    ) -> BridgeResponse:
        """Convert ACPClient (status, data) tuple to BridgeResponse."""
        if status == "SUCCESS":
            return BridgeResponse(
                status=BridgeResponseStatus.SUCCESS,
                text=data.get("response", ""),
                usage=data.get("usage"),
                tool_calls=tool_calls,
                log_path=self._client.log_path if self._client else None,
            )

        if status == "APPROVAL_NEEDED":
            return BridgeResponse(
                status=BridgeResponseStatus.APPROVAL_NEEDED,
                tool_call_id=data.get("tool_call_id"),
                tool_name=data.get("tool") or data.get("title"),
                approval_options=data.get("options", []),
                tool_calls=tool_calls,
            )

        if status == "TIMEOUT":
            return BridgeResponse(
                status=BridgeResponseStatus.TIMEOUT,
                error=data.get("error", "Timeout"),
                tool_calls=tool_calls,
            )

        return BridgeResponse(
            status=BridgeResponseStatus.FAILED,
            error=data.get("error", f"Unknown status: {status}"),
            tool_calls=tool_calls,
        )
