# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Streaming support: Strands events -> A2A frames (carrying AG-UI events) for message/stream.

The adapter symbols (StreamState / adapt / to_a2a_frames / to_wire) live in a2a_agui_adapter,
which imports a2a.types + ag_ui.core at module load. They are exposed here LAZILY via PEP 562
``__getattr__`` so that importing the lightweight ``streaming.config`` (which base_orchestrator
needs at module load for signature defaults) does NOT drag the adapter — and thus a2a/ag_ui —
into the non-streaming import path. ``StreamingConfig``/``DEFAULT_STREAMING_CONFIG`` are plain
dataclasses with no heavy deps, so they stay eager.
"""

from typing import TYPE_CHECKING, Any

from agent_builder_sdk.streaming.config import DEFAULT_STREAMING_CONFIG, StreamingConfig

if TYPE_CHECKING:  # for type checkers / IDEs only — not executed at runtime
    from agent_builder_sdk.streaming.a2a_agui_adapter import (
        StreamState,
        adapt,
        to_a2a_error_frames,
        to_a2a_frames,
        to_wire,
    )

__all__ = (
    "StreamingConfig",
    "DEFAULT_STREAMING_CONFIG",
    "StreamState",
    "adapt",
    "to_wire",
    "to_a2a_frames",
    "to_a2a_error_frames",
)

_LAZY_ADAPTER_EXPORTS = frozenset(
    {"StreamState", "adapt", "to_a2a_frames", "to_a2a_error_frames", "to_wire"}
)


def __getattr__(name: str) -> Any:
    """Lazily resolve adapter symbols on first access (PEP 562), so the heavy adapter module
    is imported only when streaming actually runs — not merely because someone imported
    ``streaming.config``."""
    if name in _LAZY_ADAPTER_EXPORTS:
        from agent_builder_sdk.streaming import a2a_agui_adapter

        return getattr(a2a_agui_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
