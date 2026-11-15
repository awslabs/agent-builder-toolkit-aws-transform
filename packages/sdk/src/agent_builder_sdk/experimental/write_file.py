# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Experimental ``write_file`` tool: the model writes a text file under /tmp in the agent's container.

An agent with no shell tool authors its files with it. The tool is opt-in: pass it in
``custom_tools``. It refuses a path outside /tmp, a relative path, a path with a ``..`` component or
a NUL byte, a symlink or directory at the path, and the agent's own runtime state (see
:mod:`agent_builder_sdk.util.paths`). It writes at most 256 KiB per call, and each write is atomic.
"""

import logging
import os
import shutil
import tempfile
import threading

from strands.tools import tool

from agent_builder_sdk.util.decorators import experimental
from agent_builder_sdk.util.paths import unwritable

logger = logging.getLogger(__name__)

_WRITE_ROOT = "/tmp"

# The cap bounds what one call puts on disk. It cannot prevent a very long ``content`` from timing
# out while the model streams it, which is why the docstring tells the model to write in sections.
_MAX_WRITE_BYTES = 256 * 1024

# An append reads the old file and replaces it, so two concurrent writes to one file would lose one.
_write_lock = threading.Lock()


def _replace(target: str, data: bytes, append: bool) -> int:
    """Write ``data`` (after the current bytes of ``target`` when ``append``) to a temp file in the
    same directory, then rename it over ``target``. Returns the new size of ``target`` in bytes."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".write_file-")
    try:
        with os.fdopen(fd, "wb") as out:
            if os.path.exists(target):
                shutil.copymode(target, tmp)
                if append:
                    with open(target, "rb") as old:
                        shutil.copyfileobj(old, out)
            out.write(data)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return os.path.getsize(target)


@tool
@experimental("write_file writes files in the agent's container, under /tmp only.")
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write text content to a file in the agent's container.

    Use this to author files (reports, HTML, scripts, configs). The content
    is written as-is, so quotes and special characters need no escaping.

    Write a long document one section per call: the first call creates the
    file, and each later call passes append=True. Do not compose a whole
    report in one call. The content is streamed to this tool while you
    generate it; past a few thousand words the call can time out before this
    tool runs, and the file is not written. At most 256 KiB per call.

    Args:
        path: Absolute file path under /tmp. Parent directories are created.
            Refused: paths outside /tmp, '..' components, symlinks,
            directories, and the agent's own runtime state.
        content: The exact text to write, encoded as UTF-8.
        append: Append to the file instead of replacing it. Defaults to False.

    Returns:
        The bytes written and the resulting file size, or an error message.
    """
    if not path or not path.strip():
        return "Error: path cannot be empty."
    if not os.path.isabs(path):
        return f"Error: path must be absolute, under {_WRITE_ROOT}."

    why = unwritable(path, [_WRITE_ROOT])
    if why:
        return f"Error: write_file cannot write there: {why}."

    encoded = content.encode("utf-8", errors="replace")
    if len(encoded) > _MAX_WRITE_BYTES:
        return (
            f"Error: content is {len(encoded)} bytes; max {_MAX_WRITE_BYTES} per call. "
            "Write the file in smaller sections using append=True."
        )

    resolved = os.path.realpath(path)
    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with _write_lock:
            total = _replace(resolved, encoded, append)
    except OSError as e:
        logger.error("write_file failed for %s: %s", resolved, e)
        return f"Error: could not write {resolved}: {e}"
    # Sizes only: the content may hold sensitive values.
    logger.info(
        "write_file %s: path=%s, bytes_written=%d, file_size=%d",
        "appended" if append else "wrote",
        resolved,
        len(encoded),
        total,
    )
    return f"{'Appended' if append else 'Wrote'} {len(encoded)} bytes to {resolved} (file is now {total} bytes)."
