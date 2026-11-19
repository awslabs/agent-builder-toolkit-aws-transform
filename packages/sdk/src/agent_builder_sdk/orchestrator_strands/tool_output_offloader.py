# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Move oversized tool results out of the model context into local files."""

import asyncio
import dataclasses
import json
import logging
import os
import re
import uuid
from contextvars import ContextVar
from typing import AbstractSet, Any, FrozenSet, List, Optional, Sequence

from strands.hooks import AfterToolCallEvent
from strands.plugins import hook
from strands.storage import LocalFileStorage
from strands.types.tools import ToolResult, ToolResultContent
from strands.vended_plugins.context_offloader import ContextOffloader

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULT_TOKENS = 12_500
DEFAULT_PREVIEW_TOKENS = 1_000
# json.loads, which checks that the text is JSON, takes several times the memory of the text.
MAX_INDENTED_JSON_CHARS = 5_000_000
_MAX_INDENT_DEPTH = 20
_INDENTS = ["\n" + "  " * depth for depth in range(_MAX_INDENT_DEPTH + 1)]
# Indentation adds up to 41 chars per token, so small values nested deeply grow about 21 times.
_MAX_INDENTED_GROWTH = 3
# A JSON string with its escapes, a structural character, or a number or literal name.
_JSON_TOKEN = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|[{}\[\],:]|[^\s{}\[\],:"]+')

# Tools whose result the model acts on as a whole: a loaded skill, recalled memory, a subagent's answer.
DEFAULT_KEEP_IN_CONTEXT_TOOLS: FrozenSet[str] = frozenset(
    {
        "skills",
        "memory",
        "discover_subagents",
        "send_message_to_subagent",
        "async_send_message_to_subagent",
        "stream_message_to_subagent",
        "send_message_to_subagent_and_relay",
    }
)


# The blocks that the handler running in the current context gave to the parent offloader.
_staged_blocks: ContextVar[List[ToolResultContent]] = ContextVar("staged_blocks")


def _is_offloadable(block: ToolResultContent) -> bool:
    return bool(block.get("text")) or "json" in block


def _relined_json(text: str) -> str:
    """Return valid JSON ``text`` with each value on its own line; literals stay byte-for-byte.

    Lines are indented by two spaces per level, up to ``_MAX_INDENT_DEPTH`` levels. When that makes
    the result longer than ``_MAX_INDENTED_GROWTH`` times ``text``, the lines are not indented, and
    the result is at most twice as long as ``text``.
    """
    parts = _relined_json_parts(text, _INDENTS)
    if sum(map(len, parts)) > _MAX_INDENTED_GROWTH * len(text):
        parts = _relined_json_parts(text, ["\n"])
    return "".join(parts)


def _relined_json_parts(text: str, indents: Sequence[str]) -> List[str]:
    """Return the tokens of ``text`` with ``indents[depth]`` (the last one when deeper) between."""
    parts: List[str] = []
    depth = 0
    deepest = len(indents) - 1
    for match in _JSON_TOKEN.finditer(text):
        token = match.group()
        opened = bool(parts) and parts[-1] in ("{", "[")
        if token in ("}", "]"):
            depth -= 1
            if not opened:
                parts.append(indents[min(depth, deepest)])
        elif opened:
            parts.append(indents[min(depth, deepest)])
        parts.append(token)
        if token in ("{", "["):
            depth += 1
        elif token == ",":
            parts.append(indents[min(depth, deepest)])
        elif token == ":":
            parts.append(" ")
    return parts


def _with_json_on_short_lines(block: ToolResultContent) -> ToolResultContent:
    """Return a text block that holds a JSON object or array with each value on its own line.

    Only whitespace between tokens changes: numbers, strings, escapes, repeated keys and key order
    stay as the tool wrote them. ``block`` is returned for any other text, for JSON that
    ``json.loads`` rejects (also when nested too deeply), and for JSON of more than
    ``MAX_INDENTED_JSON_CHARS`` characters.
    """
    text = block.get("text")
    if not text or len(text) > MAX_INDENTED_JSON_CHARS:
        return block
    try:
        if not isinstance(json.loads(text), (dict, list)):
            return block
    except (ValueError, RecursionError):
        return block
    return ToolResultContent(text=_relined_json(text))


def _with_content(result: ToolResult, content: List[ToolResultContent]) -> ToolResult:
    return ToolResult(toolUseId=result["toolUseId"], status=result["status"], content=content)


class ToolOutputOffloader(ContextOffloader):
    """Strands plugin that moves oversized tool results to files under ``storage_dir``.

    When the text and JSON blocks of a tool result exceed ``max_result_tokens``, they are written to
    ``<storage_dir>/offloaded`` and replaced in the result by a preview of about ``preview_tokens``
    tokens and one reference per stored block. The model reads the rest with the
    ``retrieve_offloaded_content`` tool that the plugin registers: by line range, by pattern, or
    whole. Image, document and other blocks stay in the result, after the preview.

    Retrieval by line range or pattern works on lines and returns at most ``max_result_tokens * 4``
    characters. A text block that holds a JSON object or array is therefore stored indented, one
    value per line. When indentation would make it more than 3 times as long as the text, the lines
    are not indented, so the stored text is at most twice as long. Only the whitespace between
    tokens changes: numbers, strings, escapes, repeated keys and key order stay as the tool wrote
    them. The indenting runs in a worker thread. JSON text is not indented when it is longer than
    ``MAX_INDENTED_JSON_CHARS`` (5,000,000) characters or when ``json.loads`` rejects it. That
    text, and any other text, is stored as the tool returned it: of a single line longer than the
    retrieval limit, only the start is readable by line range or pattern, and the rest only by a
    whole retrieval. The pattern is a regular expression that the model writes. Strands runs it on
    the event loop, line by line, with no time limit: a pattern that backtracks heavily on a long
    line blocks the loop until the search ends.

    Files are never evicted, so a reference stays valid for as long as the directory exists: for
    another agent whose offloader uses the same ``storage_dir``, and after a checkpoint restore of
    that directory. File names are generated and hold no part of the tool name, the tool-use id or
    the tool output. When the token count or the file write fails, the result stays in context
    unchanged and a warning is logged. The warning for a failed write names a generated id; a
    debug-level line of this module maps that id to the tool name and the tool-use id.

    Agents that share a conversation history must use the same ``storage_dir``: a reference is
    readable only by an offloader on the directory that holds the file. When the agent has a Strands
    sandbox (``sandbox=``), the files are written through it, inside the sandbox: they are not in the
    host ``storage_dir`` and not in its checkpoints.

    Pass it to the orchestrator through ``plugins``::

        orchestrator = AsyncBaseOrchestrator(
            system_prompt="...",
            plugins=[ToolOutputOffloader(storage_dir=storage_dir)],
        )

    Args:
        storage_dir: Directory for the files, which go to its ``offloaded`` subdirectory.
        max_result_tokens: Offload when the text and JSON blocks of a result exceed this many
            tokens, as estimated by the agent's model.
        preview_tokens: Tokens of the result to keep in context. Must be less than
            ``max_result_tokens``.
        keep_in_context_tools: Names of the tools whose results are never offloaded. Defaults to
            ``DEFAULT_KEEP_IN_CONTEXT_TOOLS``; to add a tool, pass that set united with your own.

    Raises:
        ValueError: If ``storage_dir`` is empty or a token limit is out of range.

    Attributes:
        offload_dir: The directory that holds the offloaded files.
    """

    def __init__(
        self,
        storage_dir: str,
        *,
        max_result_tokens: int = DEFAULT_MAX_RESULT_TOKENS,
        preview_tokens: int = DEFAULT_PREVIEW_TOKENS,
        keep_in_context_tools: Optional[AbstractSet[str]] = None,
    ) -> None:
        if not storage_dir:
            raise ValueError("storage_dir must be a non-empty path")
        self.offload_dir = os.path.join(storage_dir, "offloaded")
        self._keep_in_context_tools = (
            DEFAULT_KEEP_IN_CONTEXT_TOOLS if keep_in_context_tools is None else frozenset(keep_in_context_tools)
        )
        super().__init__(
            storage=LocalFileStorage(self.offload_dir),
            max_result_tokens=max_result_tokens,
            preview_tokens=preview_tokens,
            should_offload=self._should_offload_tool,
            # References stay in the conversation history for the whole job, so the files must too.
            evict_after_cycles=None,
        )

    async def _should_offload_tool(self, tool_name: str, token_count: int, **kwargs: Any) -> bool:
        if tool_name in self._keep_in_context_tools:
            return False
        # The parent calls this after it has counted the tokens of the result and before it reads the
        # blocks for the preview and the files. The line breaks go in here, so max_result_tokens
        # applies to the text as the tool returned it.
        blocks = _staged_blocks.get()
        blocks[:] = await asyncio.to_thread(lambda: [_with_json_on_short_lines(block) for block in blocks])
        return True

    async def _handle_tool_result(self, event: AfterToolCallEvent) -> None:
        """Offload the text and JSON blocks of an oversized result; keep its other blocks."""
        content = event.result["content"]
        offloadable = [block for block in content if _is_offloadable(block)]
        if not offloadable:
            return
        # The parent derives the file name from the tool-use id and pairs blocks with their stored
        # references by position. It gets a copy of the event with a generated id, so the name is
        # unique and free of model-provided text, and only the blocks it stores, so positions match.
        staged_result = _with_content(event.result, offloadable)
        offload_id = uuid.uuid4().hex
        # The parent's log lines, such as its warning for a failed write, name only the generated id.
        logger.debug(
            "Offload id %s is for tool %r, tool-use id %r",
            offload_id,
            event.tool_use.get("name"),
            event.tool_use["toolUseId"],
        )
        staged = dataclasses.replace(
            event,
            tool_use={**event.tool_use, "toolUseId": offload_id},
            result=staged_result,
        )
        token = _staged_blocks.set(offloadable)
        try:
            await super()._handle_tool_result(staged)
        except Exception:
            logger.warning(
                "Could not offload the result of tool %r; the full result stays in context",
                event.tool_use.get("name"),
                exc_info=True,
            )
            return
        finally:
            _staged_blocks.reset(token)
        if staged.result is staged_result:
            return
        kept = [block for block in content if not _is_offloadable(block) and "text" not in block]
        event.result = _with_content(staged.result, [*staged.result["content"], *kept])

    # Strands <= 1.62 registers a plugin's @hook methods by discovery; 1.63+ registers
    # self._handle_tool_result in init_agent. Mark the override only where the parent is marked, so
    # the handler is registered exactly once on either.
    if hasattr(ContextOffloader._handle_tool_result, "_hook_event_types"):
        _handle_tool_result = hook(_handle_tool_result)  # type: ignore[call-overload]
