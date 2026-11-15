# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
from typing import Any

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from strands.types.tools import ToolResultContent

from agent_builder_sdk.util.converse_image import ImageConversionError, submit_conversion

logger = logging.getLogger(__name__)


class ImageBlockGuardHook(HookProvider):
    """Keep the image blocks of tool results within 3.75 MB and 1568 px per side.

    3.75 MB is the Bedrock Converse limit: Converse rejects a request that holds a larger image,
    or an image whose bytes do not match its declared format. The tool result stays in history,
    so one such image fails every later model call of the conversation. 1568 px is not a
    Converse limit (that is 8000 px). It is the edge above which, by Anthropic's vision
    guidance, a Claude model resizes an image before it reads it. The edge is fixed, so a model
    that reads larger images still gets them downscaled. After each tool call this hook:

    - leaves a valid png, jpeg, gif or webp block of at most 3.75 MB and 1568 px per side as
      is, unless it is an animation of more than 1,000 frames or 50 million pixels over all
      its frames;
    - corrects a wrong declared format;
    - downscales and re-encodes any other image (first frame only; png when it has
      transparency, jpeg at quality 85 otherwise);
    - replaces an image that cannot be read or made to fit, that needs more than 20 million
      pixels decoded, that is over 20 MiB, or that is a JPEG with more than one Exif segment,
      with a text block that names the reason, so the model knows an image was there. The
      text never quotes the image bytes.

    A conversion can take about 350 MB of memory for a 20-million-pixel image, and two run at
    a time. Only blocks with a ``bytes`` source are checked. Other blocks keep their place and
    content.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

    async def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        result = event.result
        content = result.get("content") or []
        if not any("image" in block for block in content):
            return
        tool_name = event.tool_use.get("name", "")
        result["content"] = await asyncio.gather(
            *(self._guard(block, tool_name) for block in content)
        )

    async def _guard(self, block: ToolResultContent, tool_name: str) -> ToolResultContent:
        if "image" not in block:
            return block
        image = block["image"]
        source = image.get("source", {}).get("bytes")
        if not isinstance(source, (bytes, bytearray)):
            return block
        raw = bytes(source)
        declared = str(image.get("format", ""))
        try:
            data, fmt = await asyncio.wrap_future(submit_conversion(raw))
        except ImageConversionError as error:
            logger.warning("Dropping an image block from '%s': %s", tool_name, error)
            return {
                "text": f"[image from {tool_name}: {declared}, {len(raw):,} bytes, "
                f"not shown: {error}]"
            }
        if data is raw and fmt == declared:
            return block
        logger.info(
            "Normalized an image block from '%s': %s %d bytes -> %s %d bytes",
            tool_name,
            declared,
            len(raw),
            fmt,
            len(data),
        )
        return {"image": {"format": fmt, "source": {"bytes": data}}}
