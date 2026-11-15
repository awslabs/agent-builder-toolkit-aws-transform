# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""The ``image_reader`` tool: an image file on disk as a Converse API image block.

Derived from ``strands_tools/image_reader.py`` of strands-agents-tools 0.8 (Apache-2.0), which
0.9 removed. The tool name and input schema are the same. Modified: only a regular file of at
most MAX_IMAGE_FILE_BYTES is read, and the image is returned within 3.75 MB and 1568 px per
side (downscaled and re-encoded when needed) instead of as the raw file bytes. The function is
a coroutine: Strands awaits it on the event loop, so a call waiting for a conversion holds no
thread.

Strands registers a module-style tool under its module name, so this file must stay
``image_reader.py``.
"""

import asyncio
import os
import stat
from typing import Any

from strands.types.tools import ToolResult, ToolUse

from agent_builder_sdk.util.converse_image import MAX_INPUT_BYTES, convert_image

# Read into memory before the image header can be checked, so the size is capped first.
MAX_IMAGE_FILE_BYTES = MAX_INPUT_BYTES

TOOL_SPEC = {
    "name": "image_reader",
    "description": (
        "Reads an image file from a given path and returns it in the format required for the "
        "Converse API"
    ),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "The path to the image file",
                }
            },
            "required": ["image_path"],
        }
    },
}


async def image_reader(tool: ToolUse, **kwargs: Any) -> ToolResult:
    """Return the image at ``tool["input"]["image_path"]`` as one Converse image block.

    The path may be any file the agent process can read: ``~`` is expanded, a relative path
    is resolved against the working directory, and symbolic links are followed. The file must
    be a regular file of at most MAX_IMAGE_FILE_BYTES that holds a PNG, JPEG, GIF, WebP or BMP
    image. An image over 3.75 MB (the Converse limit) or 1568 px per side is downscaled and
    re-encoded; one that needs more than 20 million pixels decoded (40 million for a JPEG), or
    whose conversion takes more than 30 s, is an error.
    File content is returned only as an image; every failure is an ``error`` result with a
    message for the model that quotes no file content, never an exception.
    """
    tool_input = tool.get("input")
    image_path = tool_input.get("image_path") if isinstance(tool_input, dict) else None
    if not isinstance(image_path, str) or not image_path:
        return _error(tool, "File path is required")
    file_path = os.path.expanduser(image_path)
    try:
        data, image_format = await convert_image(await asyncio.to_thread(_read, file_path))
    except FileNotFoundError:
        return _error(tool, f"File not found at path: {file_path}")
    except (OSError, ValueError) as error:
        return _error(tool, f"Error reading file: {error}")
    return {
        "toolUseId": tool["toolUseId"],
        "status": "success",
        "content": [{"image": {"format": image_format, "source": {"bytes": data}}}],
    }


def _read(file_path: str) -> bytes:
    # Checked before the open: opening a FIFO blocks, and a device file has no end.
    if not stat.S_ISREG(os.stat(file_path).st_mode):
        raise ValueError("not a regular file")
    with open(file_path, "rb") as file:
        raw = file.read(MAX_IMAGE_FILE_BYTES + 1)
    if len(raw) > MAX_IMAGE_FILE_BYTES:
        raise ValueError(f"the file is over the {MAX_IMAGE_FILE_BYTES:,}-byte limit")
    return raw


def _error(tool: ToolUse, message: str) -> ToolResult:
    return {"toolUseId": tool["toolUseId"], "status": "error", "content": [{"text": message}]}
