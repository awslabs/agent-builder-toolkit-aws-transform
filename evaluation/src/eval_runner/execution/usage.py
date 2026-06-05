# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extract usage metrics from a kiro-cli session file.

The kiro-cli ACP driver does not report token usage over the wire — its prompt
responses carry only ``stopReason``. The real usage signals are persisted to the
agent's session JSON under
``session_state.conversation_metadata.user_turn_metadatas[]``:

- ``metering_usage`` — a list of ``{"value", "unit": "credit"}`` entries (cost).
- ``context_usage_percentage`` — context-window utilisation per turn.
- ``input_token_count`` / ``output_token_count`` — present but currently always
  zero from kiro-cli; summed anyway so a future driver that populates them works.

``session_state.rts_model_state.model_info.context_window_tokens`` gives the
window size.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eval_runner.models import TokenUsage

logger = logging.getLogger(__name__)


def format_usage_summary(usage: TokenUsage) -> list[str]:
    """Render human-readable usage lines for a CLI summary.

    Returns an empty list when there is no usage signal, so callers print
    nothing rather than a misleading ``0.00 credits, 0.0% context``. Shared by
    both CLI entry points so the suppression rule lives in one place.
    """
    lines: list[str] = []
    if usage.credits or usage.context_usage_percentage:
        lines.append(
            f"Usage: {usage.credits:.2f} credits, "
            f"{usage.context_usage_percentage:.1f}% context"
        )
    if usage.total_tokens > 0:
        lines.append(
            f"Tokens: {usage.total_tokens:,} total "
            f"(input: {usage.input_tokens:,}, output: {usage.output_tokens:,}"
            f", cached: {usage.cached_read_tokens:,})"
        )
    return lines


def usage_from_session_file(path: Path) -> TokenUsage:
    """Parse a kiro-cli session JSON into a :class:`TokenUsage`.

    Returns an empty :class:`TokenUsage` (all zeros) if the file is missing,
    unreadable, malformed, or lacks the expected metadata — usage is advisory,
    never a reason to fail a run.
    """
    # Every level of this parse is defensive: the session file is written by an
    # external process (kiro-cli) and may be partial/corrupt. The contract is to
    # return an empty TokenUsage rather than ever raise — usage is advisory.
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Could not read usage from session file %s: %s", path, e)
        return TokenUsage()

    state = _as_dict(_as_dict(data).get("session_state"))
    usage = TokenUsage()

    turns = _as_dict(state.get("conversation_metadata")).get("user_turn_metadatas")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            usage.input_tokens += _as_int(turn.get("input_token_count"))
            usage.output_tokens += _as_int(turn.get("output_token_count"))
            usage.credits += _sum_credits(turn.get("metering_usage"))
            pct = turn.get("context_usage_percentage")
            if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                usage.context_usage_percentage = max(usage.context_usage_percentage, pct)

    # The session file has no aggregate total — derive it from the per-turn
    # counts. (This differs from TokenUsage.add(), which reads a driver-supplied
    # "totalTokens" directly; the two paths never run for the same usage object.)
    usage.total_tokens = usage.input_tokens + usage.output_tokens

    model_info = _as_dict(_as_dict(state.get("rts_model_state")).get("model_info"))
    window = model_info.get("context_window_tokens")
    if isinstance(window, (int, float)) and not isinstance(window, bool):
        usage.context_window_tokens = int(window)

    return usage


def _as_dict(value: object) -> dict:
    """Return ``value`` if it is a dict, else an empty dict.

    Unlike ``value or {}``, this coerces *truthy* non-dicts (lists, strings)
    too, so a later ``.get()`` can't raise AttributeError on malformed input.
    """
    return value if isinstance(value, dict) else {}


def _as_int(value: object) -> int:
    """Coerce a numeric value to int, treating anything else (incl. bool/str) as 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _sum_credits(metering_usage: object) -> float:
    """Sum ``value`` over credit-unit entries in a ``metering_usage`` list."""
    if not isinstance(metering_usage, list):
        return 0.0
    total = 0.0
    for entry in metering_usage:
        if isinstance(entry, dict) and entry.get("unit") == "credit":
            value = entry.get("value")
            if isinstance(value, (int, float)):
                total += value
    return total
