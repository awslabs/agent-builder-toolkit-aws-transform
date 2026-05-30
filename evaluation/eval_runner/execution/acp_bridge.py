# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""ACP client for agent-cli ACP (Agent Client Protocol) communication.

Provides ACPClient — a JSON-RPC 2.0 client that drives agent-cli acp
as a subprocess. Handles session lifecycle, prompt dispatch, tool approval
forwarding, and token usage tracking.

Based on the Agent Communication Protocol (ACP) specification.
Daemon/CLI code removed — only ACPClient is used.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import time
from itertools import count
from typing import IO, Any, Callable


# ---------------------------------------------------------------------------
# ACP Client
# ---------------------------------------------------------------------------
class ACPClient:
    """JSON-RPC 2.0 client for a single agent-cli acp process."""

    def __init__(
        self,
        agent: str,
        log_path: str,
        cwd: str | None = None,
        verbose: bool = False,
        has_mcp: bool = False,
        binary: str = "agent-cli",
    ) -> None:
        self.agent = agent
        self.log_path = log_path
        self.cwd = cwd  # working directory for agent-cli acp process
        self.binary = binary  # ACP driver binary (e.g. "agent-cli", "kiro-cli")
        self.verbose = verbose
        self.has_mcp = has_mcp
        self.proc: subprocess.Popen[str] | None = None
        self.session_id: str | None = None
        self._msg_id = count(1)
        # Defer file handle creation to start() to avoid leaks if start() is
        # never called or raises. Handles are closed in kill().
        self._log_fh: IO[str] | None = None
        self._raw_log_fh: IO[str] | None = None
        self._stderr_fh: IO[str] | None = None
        self._pending_approval: Any = None  # rpc_id when paused
        self._agent_buf: list[str] = []  # buffer for token chunks

    def _flush_agent_buf(self) -> None:
        if self._agent_buf:
            text = "".join(self._agent_buf).strip()
            if text and self._log_fh:
                ts = time.strftime("%H:%M:%S")
                self._log_fh.write(f"[{ts}] AGENT: {text}\n")
            self._agent_buf = []

    def _log(self, direction: str, data: dict[str, Any]) -> None:
        if not self._log_fh or not self._raw_log_fh:
            return
        ts = time.strftime("%H:%M:%S")
        # Raw protocol log — every JSON-RPC message
        self._raw_log_fh.write(f"[{ts}] {direction} {json.dumps(data)}\n")
        self._raw_log_fh.flush()
        method = data.get("method", "")

        if method == "session/update":
            update = data.get("params", {}).get("update", {})
            su = update.get("sessionUpdate", "")

            if su == "agent_message_chunk":
                text = update.get("content", {}).get("text", "")
                self._agent_buf.append(text)
                return

            self._flush_agent_buf()

            if su == "tool_call":
                name = update.get("title", "?")
                kind = update.get("kind", "")
                status = update.get("status", "")
                self._log_fh.write(f"[{ts}] TOOL:  {name} ({kind}) → {status}\n")

            elif su == "tool_call_update":
                name = update.get("title", "?")
                kind = update.get("kind", "")
                status = update.get("status", "")
                raw_in = update.get("rawInput", {})
                hint = ""
                for k in ("pattern", "path", "ops", "command", "symbol_name", "query"):
                    if k in raw_in:
                        hint = f"  {k}={json.dumps(raw_in[k])[:120]}"
                        break
                if not hint and isinstance(raw_in, dict):
                    first = next(iter(raw_in.values()), None)
                    if isinstance(first, str):
                        hint = f"  {first[:120]}"
                self._log_fh.write(f"[{ts}] TOOL:  {name} ({kind}) → {status}{hint}\n")

            elif su == "approval_request":
                self._log_fh.write(f"[{ts}] APPROVAL: {json.dumps(update)[:200]}\n")

            else:
                self._log_fh.write(f"[{ts}] UPDATE: {su} {json.dumps(update)[:200]}\n")

        elif method == "session/request_permission":
            self._flush_agent_buf()
            params = data.get("params", {})
            tool = params.get("toolCall", {}).get("title", "?")
            options = [o["optionId"] for o in params.get("options", [])]
            self._log_fh.write(f"[{ts}] APPROVAL_NEEDED: tool={tool} options={options}\n")

        elif (
            "result" in data
            and isinstance(data.get("result"), dict)
            and data["result"].get("stopReason")
        ):
            self._flush_agent_buf()
            usage = data["result"].get("usage")
            if usage:
                self._log_fh.write(
                    f"[{ts}] USAGE: input={usage.get('inputTokens', 0)} output={usage.get('outputTokens', 0)} total={usage.get('totalTokens', 0)} cached_read={usage.get('cachedReadTokens', 0)}\n"
                )
            self._log_fh.write(f"[{ts}] DONE:  {data['result']['stopReason']}\n")

        elif "error" in data:
            self._flush_agent_buf()
            self._log_fh.write(f"[{ts}] ERROR: {json.dumps(data['error'])}\n")

        elif method.startswith("_kiro.dev/"):
            # Log agent-cli notifications (config errors, MCP failures, etc.)
            self._flush_agent_buf()
            params = data.get("params", {})
            self._log_fh.write(f"[{ts}] KIRO:  {method} {json.dumps(params)[:500]}\n")

        elif direction == ">>>":
            # Outgoing RPC — log compactly
            method_out = data.get("method", "")
            if method_out in ("session/prompt",):
                prompt_text = data.get("params", {}).get("prompt", "")[:200]
                self._log_fh.write(f"[{ts}] >>> {method_out}: {prompt_text}\n")
            # skip initialize/session/new noise

        self._log_fh.flush()

    def _close_file_handles(self):
        """Close all open file handles. Safe to call multiple times."""
        for fh in (self._log_fh, self._raw_log_fh, self._stderr_fh):
            if fh and not fh.closed:
                try:
                    fh.close()
                except Exception:
                    pass

    def start(self):
        # Open log file handles here (not in __init__) so they don't leak
        # if start() is never called or raises partway through.
        try:
            self._log_fh = open(self.log_path, "a")
            self._raw_log_fh = open(self.log_path.replace(".log", "-raw.log"), "a")
            stderr_path = self.log_path.replace(".log", "-stderr.log")
            self._stderr_fh = open(stderr_path, "a")

            # Set per-session agent-cli log file so each scenario gets its own
            # kiro-chat log instead of sharing the global one.
            kiro_log_path = self.log_path.replace(".log", "-kiro.log")
            env = os.environ.copy()
            env["KIRO_CHAT_LOG_FILE"] = kiro_log_path
            if self.verbose:
                env["KIRO_LOG_LEVEL"] = "debug"
            self.kiro_log_path = kiro_log_path

            self.proc = subprocess.Popen(
                [self.binary, "acp", "--agent", self.agent],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_fh,
                env=env,
                text=True,
                bufsize=1,
                cwd=self.cwd,  # workspace dir for agent discovery (.kiro/agents/)
                start_new_session=True,  # own process group so we can kill all children
            )
            self._initialize()
            self._create_session()
        except Exception:
            if self.proc and self.proc.poll() is None:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                    self.proc.wait(timeout=5)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self._close_file_handles()
            raise

    def _write(self, msg: dict[str, Any]) -> None:
        self._log(">>>", msg)
        assert self.proc and self.proc.stdin, "ACP process not started"
        raw = json.dumps(msg)
        self.proc.stdin.write(raw + "\n")
        self.proc.stdin.flush()

    def _send(self, method, params=None):
        msg = {"jsonrpc": "2.0", "id": next(self._msg_id), "method": method, "params": params or {}}
        self._write(msg)
        return self._read_result()

    def _read_result(self, timeout: int = 30) -> dict[str, Any] | None:
        assert self.proc and self.proc.stdout, "ACP process not started"
        deadline = time.time() + timeout
        for _ in range(2000):
            remaining = deadline - time.time()
            if remaining <= 0:
                raise RuntimeError("Timeout waiting for ACP response")
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                raise RuntimeError("Timeout waiting for ACP response")
            line = self.proc.stdout.readline()
            if not line:
                return None
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._log("<<<", data)
            if "error" in data:
                raise RuntimeError(f"ACP error: {data['error']}")
            if "result" in data:
                return data["result"]
        return None

    def _initialize(self):
        self._send(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
                "clientInfo": {"name": "agent-eval-bridge", "version": "1.0.0"},
            },
        )

    def _create_session(self):
        result = self._send("session/new", {"cwd": self.cwd or os.getcwd(), "mcpServers": []})
        if not result or "sessionId" not in result:
            raise RuntimeError(f"Failed to create session: {result}")
        self.session_id = result["sessionId"]
        self.current_mode = result.get("modes", {}).get("currentModeId", "")
        # NOTE: agent-cli sends _kiro.dev/mcp/server_initialized almost immediately
        # after session/new, but the MCP server is NOT fully ready at that point.
        # It still needs time to register tools, load auth config, and connect to
        # backend services. Sending prompts too early causes agent-cli to delay or
        # drop MCP tool dispatches (tool_call events arrive but tool_call_update
        # completions never come). A 20s sleep reliably avoids this.
        if self.has_mcp:
            if self._log_fh:
                ts = time.strftime("%H:%M:%S")
                self._log_fh.write(f"[{ts}] WAIT:  draining notifications for 20s (MCP warm-up)\n")
                self._log_fh.flush()
            self._drain_notifications(timeout=20)

    def _drain_notifications(self, timeout: int = 20) -> None:
        """Read and log notifications for the given duration.

        Drains the agent-cli stdout pipe during MCP warm-up, logging all
        events (server_initialized, commands/available, metadata, etc.)
        instead of letting them buffer unread during a sleep.
        """
        assert self.proc and self.proc.stdout, "ACP process not started"
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            ready, _, _ = select.select([self.proc.stdout], [], [], min(remaining, 1.0))
            if not ready:
                continue  # keep waiting until timeout
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._log("<<<", data)

    def prompt(
        self,
        text: str,
        timeout: int = 7200,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Send prompt. Returns (status, data) where status is SUCCESS/TIMEOUT/FAILED/APPROVAL_NEEDED."""
        assert self.proc and self.proc.stdout, "ACP process not started"
        if self.proc.poll() is not None:
            return "FAILED", {"error": "ACP process died"}

        msg = {
            "jsonrpc": "2.0",
            "id": next(self._msg_id),
            "method": "session/prompt",
            "params": {"sessionId": self.session_id, "prompt": [{"type": "text", "text": text}]},
        }
        self._write(msg)

        chunks: list[str] = []
        deadline = time.time() + timeout
        pending_end_turn = False
        tool_in_progress = False
        last_usage = None  # token usage from PromptResponse
        # agent-cli can take 30-60s between last agent text and end_turn
        # (internal processing). When we have text, extend the deadline.
        end_turn_grace = 90  # extra seconds to wait for end_turn after receiving text
        grace_applied = False
        last_activity = time.time()
        flush_id = None

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            ready, _, _ = select.select([self.proc.stdout], [], [], min(remaining, 1.0))
            if not ready:
                # If no activity for 20s, send a no-op to flush agent-cli's
                # stdout buffer. agent-cli may hold request_permission events
                # in its outgoing actor without flushing to the pipe.
                # session/cancel returns "Method not found" but the error
                # response forces a pipe flush, unblocking any buffered
                # request_permission that was waiting.
                #
                # Evidence: in auto-handle-rejected, flush at 04:04:59
                # immediately unblocked a request_permission that had been
                # buffered for 240s. However, this only helps when the delay
                # is caused by stdout buffering — it cannot accelerate
                # genuinely slow tool execution (e.g., AWS Tranform custom def exec
                # running a real transformation for 10+ minutes).
                if flush_id is None and (time.time() - last_activity) >= 20:
                    flush_id = next(self._msg_id)
                    flush_msg = {
                        "jsonrpc": "2.0",
                        "id": flush_id,
                        "method": "session/cancel",
                        "params": {"sessionId": self.session_id},
                    }
                    self._write(flush_msg)
                    if self._log_fh:
                        ts = time.strftime("%H:%M:%S")
                        self._log_fh.write(f"[{ts}] FLUSH: sent session/cancel to flush stdout\n")
                        self._log_fh.flush()
                continue  # re-check deadline
            line = self.proc.stdout.readline()
            if not line:
                return "FAILED", {"error": "ACP process EOF"}
            last_activity = time.time()
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._log("<<<", data)

            # Ignore "Method not found" error from our flush cancel
            if flush_id is not None and data.get("id") == flush_id:
                flush_id = None
                continue

            # Handle JSON-RPC error responses (e.g., usage limits, internal errors).
            # Without this, errors from session/prompt fall through all checks and
            # the loop spins until the timeout deadline.
            if "error" in data and "id" in data and data.get("id") != flush_id:
                error = data["error"]
                error_msg = error.get("message", "Unknown error")
                error_data = error.get("data", "")
                return "FAILED", {"error": f"{error_msg}: {error_data}"}

            # Track tool call lifecycle
            if data.get("method") == "session/update":
                update = data.get("params", {}).get("update", {})
                su = update.get("sessionUpdate")
                if su == "tool_call":
                    status = update.get("status")
                    title = update.get("title", "")
                    if status == "in_progress":
                        tool_in_progress = True
                        if on_event:
                            on_event(
                                {
                                    "type": "status",
                                    "tool": title,
                                    "kind": update.get("kind", ""),
                                    "status": "in_progress",
                                }
                            )
                    elif status in ("success", "error"):
                        tool_in_progress = False
                        chunks = []  # next chunks = new agent message
                        if on_event:
                            on_event(
                                {
                                    "type": "status",
                                    "tool": title,
                                    "kind": update.get("kind", ""),
                                    "status": status,
                                }
                            )
                        if pending_end_turn:
                            return "SUCCESS", {"response": "".join(chunks), "usage": last_usage}
                    elif title and on_event:
                        # Title-update message (no status) — emit updated descriptive title
                        on_event(
                            {
                                "type": "status",
                                "tool": title,
                                "kind": update.get("kind", ""),
                                "status": "in_progress",
                            }
                        )
                elif su == "tool_call_update":
                    if update.get("status") == "completed":
                        tool_in_progress = False
                        chunks = []  # next chunks = new agent message
                        if on_event:
                            on_event(
                                {
                                    "type": "status",
                                    "tool": update.get("title", ""),
                                    "kind": update.get("kind", ""),
                                    "status": "completed",
                                    "raw_output": update.get("rawOutput"),
                                }
                            )
                        if pending_end_turn:
                            return "SUCCESS", {"response": "".join(chunks), "usage": last_usage}
                elif su == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        text = content.get("text", "")
                        chunks.append(text)
                        if on_event and text.strip():
                            on_event({"type": "agent_text", "text": text})
                        # Extend deadline when we have text — end_turn may be slow
                        if not grace_applied and chunks:
                            deadline = max(deadline, time.time() + end_turn_grace)
                            grace_applied = True
                continue

            # Prompt complete
            if (
                "result" in data
                and isinstance(data["result"], dict)
                and data["result"].get("stopReason")
            ):
                last_usage = data["result"].get("usage")
                if tool_in_progress:
                    pending_end_turn = True  # wait for tool to finish
                else:
                    return "SUCCESS", {"response": "".join(chunks), "usage": last_usage}
                continue

            # Tool approval request — pause and return to caller
            if data.get("method") == "session/request_permission" and "id" in data:
                params = data.get("params", {})
                tool_call = params.get("toolCall", {})
                self._pending_approval = data["id"]
                return "APPROVAL_NEEDED", {
                    "tool_call_id": tool_call.get("toolCallId", ""),
                    "tool": tool_call.get("title", ""),
                    "title": tool_call.get("title", ""),
                    "options": [o["optionId"] for o in params.get("options", [])],
                }

        return "TIMEOUT", {"error": f"Exceeded {timeout}s"}

    def send_approval(
        self,
        option: str,
        timeout: int = 7200,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resume after APPROVAL_NEEDED. Returns (status, data) for the rest of the prompt."""
        if self._pending_approval is None:
            return "FAILED", {"error": "No pending approval"}
        assert self.proc and self.proc.stdout, "ACP process not started"
        rpc_id = self._pending_approval
        self._pending_approval = None
        self._write(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"outcome": {"outcome": "selected", "optionId": option}},
            }
        )

        # Continue reading the prompt response (select-based to honour timeout).
        # NOTE: Unlike prompt(), this doesn't track tool_in_progress/pending_end_turn.
        # After approval, agent-cli resumes the tool that was waiting, so a stopReason
        # arriving here means the turn truly ended. If this causes premature returns
        # in practice, add the same lifecycle tracking as prompt().
        chunks: list[str] = []
        deadline = time.time() + timeout
        last_activity = time.time()
        flush_id = None
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            ready, _, _ = select.select([self.proc.stdout], [], [], min(remaining, 1.0))
            if not ready:
                # Same flush mechanism as prompt(): send a no-op to unblock
                # buffered request_permission events from agent-cli's stdout.
                if flush_id is None and (time.time() - last_activity) >= 20:
                    flush_id = next(self._msg_id)
                    flush_msg = {
                        "jsonrpc": "2.0",
                        "id": flush_id,
                        "method": "session/cancel",
                        "params": {"sessionId": self.session_id},
                    }
                    self._write(flush_msg)
                    if self._log_fh:
                        ts = time.strftime("%H:%M:%S")
                        self._log_fh.write(
                            f"[{ts}] FLUSH: sent session/cancel to flush stdout (approval)\n"
                        )
                        self._log_fh.flush()
                continue
            line = self.proc.stdout.readline()
            if not line:
                return "FAILED", {"error": "ACP process EOF after approval"}
            last_activity = time.time()
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._log("<<<", data)

            # Ignore "Method not found" error from our flush cancel
            if flush_id is not None and data.get("id") == flush_id:
                flush_id = None
                continue

            if (
                "result" in data
                and isinstance(data["result"], dict)
                and data["result"].get("stopReason")
            ):
                return "SUCCESS", {
                    "response": "".join(chunks),
                    "usage": data["result"].get("usage"),
                }

            # Another approval in same prompt
            if data.get("method") == "session/request_permission" and "id" in data:
                params = data.get("params", {})
                tool_call = params.get("toolCall", {})
                self._pending_approval = data["id"]
                return "APPROVAL_NEEDED", {
                    "tool_call_id": tool_call.get("toolCallId", ""),
                    "tool": tool_call.get("title", ""),
                    "title": tool_call.get("title", ""),
                    "options": [o["optionId"] for o in params.get("options", [])],
                }

            if data.get("method") == "session/update":
                update = data.get("params", {}).get("update", {})
                su = update.get("sessionUpdate")
                if su == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        text = content.get("text", "")
                        chunks.append(text)
                        if on_event and text.strip():
                            on_event({"type": "agent_text", "text": text})
                elif su in ("tool_call", "tool_call_update") and on_event:
                    title = update.get("title", "")
                    kind = update.get("kind", "")
                    status = update.get("status", "in_progress")
                    event: dict[str, Any] = {
                        "type": "status",
                        "tool": title,
                        "kind": kind,
                        "status": status,
                    }
                    if su == "tool_call_update":
                        event["raw_output"] = update.get("rawOutput")
                    on_event(event)

        return "TIMEOUT", {"error": f"send_approval exceeded {timeout}s"}

    def alive(self):
        return self.proc and self.proc.poll() is None

    def kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except Exception:
                    self.proc.kill()
        self._close_file_handles()
