# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Container path checks for file tools that the model drives (for example ``write_file``).

A path is allowed when it resolves (symlinks followed, ``..`` collapsed) under one of the tool's
roots and not into the agent's own runtime state. The runtime state is a process-wide set: the SDK
defaults below, plus every directory that a server or repository registers with :func:`protect`.
"""

import os
from typing import Iterable, Optional, Sequence, Set

# Default runtime-state locations of the SDK and of the agentic MCP server's log files, all under
# /tmp. A component that takes a custom location must call protect() for it (the runtime servers
# and the checkpoint repository do).
_DEFAULT_PROTECTED = (
    "/tmp/agent_runtime",
    "/tmp/orchestrator_agent",
    "/tmp/sub_agent",
    "/tmp/agent_state",
    "/tmp/agent_queue",
    "/tmp/agent_responses",
    "/tmp/conversations",
    "/tmp/atx-mcp-server.log",
    "/tmp/qt-mcp-server.log",
)

_protected: Set[str] = {os.path.realpath(path) for path in _DEFAULT_PROTECTED}


def protect(root: str) -> None:
    """Refuse ``root`` and everything below it to the file tools, even under an allowed root.

    ``root`` may be a directory or a single file. A tool root that lies inside ``root`` stays
    allowed below itself.
    """
    _protected.add(os.path.realpath(root))


def _deepest(real: str, bases: Iterable[str]) -> str:
    """The longest of ``bases`` that is ``real`` or one of its parent dirs, else ""."""
    return max(
        (base for base in bases if real == base or real.startswith(base.rstrip(os.sep) + os.sep)),
        key=len,
        default="",
    )


def is_under(path: str, roots: Sequence[str]) -> bool:
    """Whether ``path`` resolves to one of ``roots`` or below, and not into protected state unless
    a root deeper than that state holds it. ``path`` must not hold a NUL byte."""
    real = os.path.realpath(path)
    allowed = _deepest(real, [os.path.realpath(root) for root in roots])
    return bool(allowed) and len(allowed) > len(_deepest(real, _protected))


def unreadable(path: str, roots: Sequence[str]) -> Optional[str]:
    """Why a file tool must not read ``path`` (None if it may)."""
    if "\0" in path:
        return "the path holds a NUL byte"
    if ".." in path.split(os.sep):
        return f"{path} holds a '..' component"
    if is_under(path, roots):
        return None
    if _deepest(os.path.realpath(path), _protected):
        return f"{path} is this agent's own runtime state"
    return f"{path} is not under {', '.join(roots)}"


def unwritable(path: str, roots: Sequence[str]) -> Optional[str]:
    """Why a file tool must not write ``path`` (None if it may): the checks of :func:`unreadable`,
    and ``path`` must not be a directory, end in a separator or be a symlink itself."""
    why = unreadable(path, roots)
    if why:
        return why
    if os.path.islink(path):
        return f"{path} is a symlink"
    if os.path.isdir(path) or path.endswith(os.sep):
        return f"{path} is a directory, not a file"
    return None
