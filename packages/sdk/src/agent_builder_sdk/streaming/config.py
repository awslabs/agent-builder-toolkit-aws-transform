# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Config for the agent's streaming behavior."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamingConfig:
    """Configures the agent's streaming (message/stream) path.

    Passing a ``StreamingConfig`` to the server IS the opt-in to streaming — there is no
    separate enable flag. Absent (``None``) the server does not serve message/stream and
    behaves exactly as before; present, the streaming path is stood up with these settings.

    Fields:
    - ``agent_idle_ttl_seconds`` — evict a per-source streaming agent that hasn't streamed in
      this long (default 30 min), lazily on the next streaming turn, so a long-lived session
      serving many distinct sources stays memory-bounded. Nothing durable is lost: history and
      memory live in the shared stores and the agent is rebuilt on the next turn.
    - ``emit_reasoning`` / ``emit_tool_calls`` — whether to emit that event category. Both
      default on; turning one off applies to BOTH the live stream and persistence, so a
      category turned off does not reappear on refresh. The run lifecycle (RUN_STARTED /
      RUN_FINISHED / RUN_ERROR) and the assistant's text (narration + final answer) are always
      emitted — there is no toggle to suppress the answer itself.
    - ``turn_timeout_seconds`` — server-side total budget for one streaming turn (wall-clock from
      turn start). If the turn produces no terminal within this window (e.g. a hung MCP tool), the
      stream is closed with a clean terminal RUN_ERROR instead of hanging. The same budget also
      bounds a sub-agent's own streaming turn (see ``base_subagent``), which is the stream the
      ``send_message_to_subagent_and_relay`` tool consumes — so a sub-agent's turn stays capped even
      when relayed. This is one of only two true total-cap timeouts in the whole streaming path; the
      other is the client's own stream cap. Every intermediate platform hop has only an *idle*
      timeout (max gap between frames), not a total cap on the streaming connection, so none of
      them severs a healthy long stream.
    """

    agent_idle_ttl_seconds: float = 30 * 60
    emit_reasoning: bool = True
    emit_tool_calls: bool = True
    turn_timeout_seconds: float = 9 * 60


DEFAULT_STREAMING_CONFIG = StreamingConfig()
