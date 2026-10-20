# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Pool of per-source streaming agents for concurrent streaming (opt-in).

The job agent is job-scoped, not user-scoped: every caller streaming against that job
shares the same process. Strands allows only one invocation at a time per Agent object
(it raises ConcurrencyException otherwise), so a single shared agent cannot serve two
concurrent streams at once.

When streaming is enabled (a ``StreamingConfig`` is passed), this pool hands each source its
own lazily-created Agent object (built by the partner's own factory). The expensive,
concurrency-safe pieces stay shared: the Bedrock model and the MCP client (the MCP
protocol multiplexes concurrent tool calls over one connection by request id). Only
the per-Agent state that would otherwise collide — the invocation lock, agent state,
and the per-source conversation file — is separated.

The pool key, ``source_id``, is just a string — the pool never interprets it. Where it comes
from is decided upstream by ``classify_source`` (in
``orchestrator_strands.conversation.constants``): a human turn keys on ``userId``, an agent
caller on ``agentInstanceId``. Because that decision lives in one place, adding a new caller
kind needs no change here. ``source_type`` is passed only to make the logs specific.

Agents are created on first request for a source and reused after, so a source that
never streams costs nothing. Idle agents are evicted lazily (see ``idle_ttl_seconds``)
so a long-lived session that serves many distinct sources does not grow without bound.
"""

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Dict

from agent_builder_sdk.interfaces import AnyBaseAgent
from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType

logger = logging.getLogger(__name__)

_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.-]")

# Default idle TTL: evict a source's agent if it hasn't streamed in this long. 30 min is
# far larger than the max turn duration (~10 min), so an idle-evicted entry can never have
# an in-flight turn. Nothing durable is lost on eviction — conversation history and memory
# live in the shared, injected stores; the agent is rebuilt on the source's next turn.
_DEFAULT_IDLE_TTL_SECONDS = 30 * 60

# What the source_id means for each source type, for human-readable logs.
_SOURCE_ID_FIELD = {
    MessageSourceType.USER: "userId",
    MessageSourceType.SUBAGENT: "agentInstanceId",
    MessageSourceType.NOTIFICATION: "systemSource",
}


def _safe_dir_name(source_id: str) -> str:
    """Make a filesystem-safe directory name from a source id (user/agent id)."""
    return _UNSAFE_PATH_CHARS.sub("_", source_id)[:128] or "unknown"


def _source_field(source_type: MessageSourceType) -> str:
    """Name of the id field for this source type (for logs), e.g. 'userId'."""
    return _SOURCE_ID_FIELD.get(source_type, "source")


class StreamingAgentPool:
    """Lazily builds and caches one streaming agent per source id.

    The pool is scoped to a single AgentCore runtime session (one job, one process). It
    caches one agent per distinct source id and evicts entries idle longer than
    ``idle_ttl_seconds``, so memory stays bounded by the number of *recently active*
    sources rather than every source seen for the session's lifetime.

    Args:
        create_agent: Coroutine that builds an agent for a given per-source storage
            directory. The pool supplies the directory; everything else (shared model,
            shared MCP client, agent params) is closed over by the caller.
        base_storage_dir: Base directory; each source gets ``<base>/sources/<source_id>``.
            This per-source directory scopes only per-agent scratch. Conversation history
            and memory are NOT per-file: shared, injected stores are used by every
            per-source agent, keyed by ``source_id`` inside the one shared store, so an
            evicted-then-rebuilt agent recalls everything.
        idle_ttl_seconds: Evict an agent whose last use was more than this long ago
            (lazily, on the next ``get_agent`` call). Defaults to 30 minutes.
    """

    def __init__(
        self,
        create_agent: Callable[[str], Awaitable[AnyBaseAgent]],
        base_storage_dir: str,
        idle_ttl_seconds: float = _DEFAULT_IDLE_TTL_SECONDS,
    ) -> None:
        # A non-positive TTL would evict on every sweep (0 => "now - last > 0" for any prior
        # turn; negative => always), silently defeating the pool's purpose (rebuild every turn).
        # Reject it rather than surprise the operator; use a large value for "effectively never".
        if idle_ttl_seconds <= 0:
            raise ValueError(
                f"idle_ttl_seconds must be positive (got {idle_ttl_seconds}); a non-positive "
                "value would evict agents every sweep and defeat pooling. Use a large value to "
                "effectively disable eviction."
            )
        self._create_agent = create_agent
        self._base_storage_dir = base_storage_dir
        self._idle_ttl_seconds = idle_ttl_seconds
        self._agents: Dict[str, AnyBaseAgent] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_used: Dict[str, float] = {}
        # In-flight turn count per source. An entry with count > 0 has a turn actively
        # streaming and must never be evicted (eviction would let a concurrent same-source
        # turn build a SECOND agent, bypassing the one-invocation-per-source guarantee).
        self._in_flight: Dict[str, int] = {}
        self._pool_lock = asyncio.Lock()

    async def get_agent(self, source_id: str, source_type: MessageSourceType) -> AnyBaseAgent:
        """Return this source's agent, creating it on first use."""
        field = _source_field(source_type)
        safe_id = _safe_dir_name(source_id)

        self._evict_idle()

        # Fast path: already built.
        agent = self._agents.get(source_id)
        if agent is not None:
            self._last_used[source_id] = time.monotonic()
            logger.debug("Reusing streaming agent for %s %s", field, safe_id)
            return agent

        # Per-source creation lock (double-checked) so two concurrent first turns
        # for the same source don't build two agents.
        async with self._pool_lock:
            lock = self._locks.setdefault(source_id, asyncio.Lock())
        async with lock:
            agent = self._agents.get(source_id)
            if agent is None:
                source_storage_dir = os.path.join(self._base_storage_dir, "sources", safe_id)
                os.makedirs(source_storage_dir, exist_ok=True)
                agent = await self._create_agent(source_storage_dir)
                self._agents[source_id] = agent
                logger.info(
                    "Created streaming agent for %s %s (pooled agents: %d)",
                    field,
                    safe_id,
                    len(self._agents),
                )
            self._last_used[source_id] = time.monotonic()
            return agent

    @asynccontextmanager
    async def lease(self, source_id: str) -> AsyncIterator[None]:
        """Mark a source in-flight for the full duration of a streaming turn.

        Wrap the ENTIRE turn (the stream loop) in this so ``_evict_idle`` can't evict the
        agent mid-stream, regardless of how the TTL compares to turn duration. Reference-counted
        so it is safe even if a source has overlapping leases. Releasing refreshes idle time so
        the TTL is measured from the turn's END.
        """
        self._in_flight[source_id] = self._in_flight.get(source_id, 0) + 1
        try:
            yield
        finally:
            n = self._in_flight.get(source_id, 0) - 1
            if n <= 0:
                self._in_flight.pop(source_id, None)
            else:
                self._in_flight[source_id] = n
            self._last_used[source_id] = time.monotonic()

    def _evict_idle(self) -> None:
        """Drop agents idle longer than the TTL. Called opportunistically on get_agent
        (no background thread — sweeps happen exactly when the pool is next touched).

        NEVER evicts a source with an in-flight turn (``_in_flight`` count > 0), so an agent
        is never pulled out from under a running stream regardless of how the TTL compares to
        turn duration. This whole method runs synchronously (no await), so on the single asyncio
        thread it is atomic w.r.t. other coroutines — no check-then-act race.
        """
        now = time.monotonic()
        stale = [
            sid for sid, last in self._last_used.items() if now - last > self._idle_ttl_seconds
        ]
        for sid in stale:
            if self._in_flight.get(sid, 0) > 0:
                continue  # in-flight turn — never evict mid-stream
            self._agents.pop(sid, None)
            self._locks.pop(sid, None)
            self._last_used.pop(sid, None)
            logger.info(
                "Evicted idle streaming agent for source %s (pooled agents: %d)",
                _safe_dir_name(sid),
                len(self._agents),
            )
