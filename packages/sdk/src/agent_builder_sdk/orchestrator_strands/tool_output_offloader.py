# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Move oversized tool results out of the model context into local files."""

import dataclasses
import logging
import os
import uuid
from typing import AbstractSet, Any, FrozenSet, List, Optional

from strands.hooks import AfterToolCallEvent
from strands.plugins import hook
from strands.storage import LocalFileStorage
from strands.types.tools import ToolResult, ToolResultContent
from strands.vended_plugins.context_offloader import ContextOffloader

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULT_TOKENS = 12_500
DEFAULT_PREVIEW_TOKENS = 1_000

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


def _is_offloadable(block: ToolResultContent) -> bool:
    return bool(block.get("text")) or "json" in block


def _with_content(result: ToolResult, content: List[ToolResultContent]) -> ToolResult:
    return ToolResult(toolUseId=result["toolUseId"], status=result["status"], content=content)


class ToolOutputOffloader(ContextOffloader):
    """Strands plugin that moves oversized tool results to files under ``storage_dir``.

    When the text and JSON blocks of a tool result exceed ``max_result_tokens``, they are written to
    ``<storage_dir>/offloaded`` and replaced in the result by a preview of about ``preview_tokens``
    tokens and one reference per stored block. The model reads the rest with the
    ``retrieve_offloaded_content`` tool that the plugin registers: by line range, by pattern, or
    whole. Image, document and other blocks stay in the result, after the preview.

    Files are never evicted, so a reference stays valid for as long as the directory exists: for
    another agent whose offloader uses the same ``storage_dir``, and after a checkpoint restore of
    that directory. File names are generated and hold no part of the tool name, the tool-use id or
    the tool output. When the token count or the file write fails, the result stays in context
    unchanged and a warning is logged.

    Pass it to the orchestrator through ``plugins``::

        orchestrator = AsyncBaseOrchestrator(
            system_prompt="...",
            plugins=[ToolOutputOffloader(storage_dir=storage_dir)],
        )

    Args:
        storage_dir: The agent's storage directory. Files go to its ``offloaded`` subdirectory.
        max_result_tokens: Offload when the text and JSON blocks of a result exceed this many
            tokens, as estimated by the agent's model.
        preview_tokens: Tokens of the result to keep in context. Must be less than
            ``max_result_tokens``.
        keep_in_context_tools: Names of the tools whose results are never offloaded. Defaults to
            ``DEFAULT_KEEP_IN_CONTEXT_TOOLS``; to add a tool, pass that set united with your own.

    Attributes:
        offload_dir: The directory that holds the offloaded files.

    Raises:
        ValueError: If ``storage_dir`` is empty or a token limit is out of range.
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

    def _should_offload_tool(self, tool_name: str, token_count: int, **kwargs: Any) -> bool:
        return tool_name not in self._keep_in_context_tools

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
        staged = dataclasses.replace(
            event,
            tool_use={**event.tool_use, "toolUseId": uuid.uuid4().hex},
            result=staged_result,
        )
        try:
            await super()._handle_tool_result(staged)
        except Exception:
            logger.warning(
                "Could not offload the result of tool %r; the full result stays in context",
                event.tool_use.get("name"),
                exc_info=True,
            )
            return
        if staged.result is staged_result:
            return
        kept = [block for block in content if not _is_offloadable(block) and "text" not in block]
        event.result = _with_content(staged.result, [*staged.result["content"], *kept])

    # Strands <= 1.62 registers a plugin's @hook methods by discovery; 1.63+ registers
    # self._handle_tool_result in init_agent. Mark the override only where the parent is marked, so
    # the handler is registered exactly once on either.
    if hasattr(ContextOffloader._handle_tool_result, "_hook_event_types"):
        _handle_tool_result = hook(_handle_tool_result)  # type: ignore[call-overload]
