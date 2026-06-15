# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Runtime confinement of an agent's tool use to a single writable directory.

Both the evolver and the analyst run a Claude agent under
``permission_mode="acceptEdits"`` over content that ultimately derives from an
agent-under-test's own transcripts — a prompt-injection surface. An absolute or
``..`` ``file_path`` could otherwise write anywhere the operator can.

Why a ``PreToolUse`` hook and not the ``can_use_tool`` callback: ``acceptEdits``
auto-approves every Write/Edit, and the SDK documents that ``can_use_tool`` is
*not* invoked for tool calls already permitted by ``allowed_tools`` /
``permission_mode`` (claude_agent_sdk ``types.py``: "To observe or gate every
tool call regardless of permission rules, use a ``PreToolUse`` hook via
``hooks`` instead"). So a ``can_use_tool`` callback is dead code for exactly the
Write/Edit calls it is meant to confine. A ``PreToolUse`` hook fires for every
tool call, so the gate actually runs.

Defense in depth: callers should *also* pin ``tools`` to the minimal set so
Bash/NotebookEdit are not even available to the model (``allowed_tools`` only
auto-approves — it does not restrict availability). This hook additionally
default-denies any tool it does not recognize, so if that availability
restriction ever drifts open the gate still fails closed.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import HookMatcher

# Read-only tools: no path confinement needed. Reading is not the
# injection -> arbitrary-write chain we are closing, and the analyst legitimately
# reads outside its writable root (artifacts + target source).
READ_TOOLS = {"Read", "Glob", "Grep"}

# Edit tools mapped to the ``tool_input`` key that carries their target path.
# NotebookEdit uses ``notebook_path``; the others use ``file_path``.
WRITE_TOOL_PATH_KEYS = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


def confine_decision(
    tool_name: str, tool_input: dict, writable_root: Path
) -> tuple[bool, str]:
    """Pure allow/deny decision for a single tool call.

    Returns ``(allow, reason)``. ``reason`` is empty when allowed and a
    human-readable explanation when denied.

    - Read/Glob/Grep: always allowed (reads are not confined).
    - Write/Edit/MultiEdit/NotebookEdit: allowed only if the resolved target
      path stays inside ``writable_root``.
    - Anything else (e.g. Bash): denied. Fail closed, not open.
    """
    if tool_name in READ_TOOLS:
        return True, ""

    path_key = WRITE_TOOL_PATH_KEYS.get(tool_name)
    if path_key is None:
        # Default-deny an unrecognized tool. With ``tools`` pinned this should be
        # unreachable, but if availability ever drifts open (e.g. Bash) we refuse
        # rather than fall through to allow.
        return False, (
            f"{tool_name} is not permitted. The agent may only read files and "
            f"edit files inside {writable_root}."
        )

    raw = (tool_input or {}).get(path_key)
    if not raw:
        return False, f"{tool_name} called without a {path_key}."

    # Resolve relative paths against the writable root (the agent's cwd),
    # mirroring the SDK, then require the result to stay inside it.
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = writable_root / candidate
    resolved = candidate.resolve()

    if resolved == writable_root or writable_root in resolved.parents:
        return True, ""

    return False, (
        f"Refusing {tool_name} to {raw!r}: path resolves to {resolved}, outside "
        f"the writable directory {writable_root}. Only edit files inside it."
    )


def make_pre_tool_use_hook(writable_root: Path):
    """Build a ``PreToolUse`` hook callback that confines writes to ``writable_root``.

    The returned coroutine matches the SDK ``HookCallback`` signature
    ``(input_data, tool_use_id, context)`` and returns a ``PreToolUse``
    hook-specific output carrying an explicit allow/deny ``permissionDecision``.
    A ``deny`` here blocks the call even under ``acceptEdits``.
    """
    writable_root = Path(writable_root).resolve()

    async def pre_tool_use(input_data, tool_use_id, context):
        data = input_data or {}
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {}) or {}
        allow, reason = confine_decision(tool_name, tool_input, writable_root)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allow else "deny",
                "permissionDecisionReason": reason,
            }
        }

    return pre_tool_use


def confinement_hooks(writable_root: Path) -> dict:
    """Return a ``hooks=`` mapping that confines writes to ``writable_root``.

    ``matcher=None`` registers the hook for *every* tool so the default-deny
    branch sees unrecognized tools too (not just the write tools).
    """
    return {
        "PreToolUse": [HookMatcher(hooks=[make_pre_tool_use_hook(writable_root)])],
    }
