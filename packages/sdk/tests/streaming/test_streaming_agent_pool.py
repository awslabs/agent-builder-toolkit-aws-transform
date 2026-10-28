# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for StreamingAgentPool (per-source lazy agents for concurrent streaming)."""

import asyncio
import os

from agent_builder_sdk.orchestrator_strands.conversation.constants import MessageSourceType
from agent_builder_sdk.server.streaming_agent_pool import (
    StreamingAgentPool,
    _safe_dir_name,
    _source_field,
)

USER = MessageSourceType.USER
SUBAGENT = MessageSourceType.SUBAGENT


def make_pool(base_dir):
    """Pool whose create_agent returns a lightweight sentinel and records the
    per-source storage dir it was given."""
    created = []

    async def create_agent(source_storage_dir):
        created.append(source_storage_dir)
        # return a unique object per call so identity checks are meaningful
        return object()

    pool = StreamingAgentPool(create_agent=create_agent, base_storage_dir=base_dir)
    return pool, created


async def test_creates_on_first_use_and_caches(tmp_path):
    pool, created = make_pool(str(tmp_path))

    a1 = await pool.get_agent("userA", USER)
    assert len(created) == 1  # built on first request

    a1_again = await pool.get_agent("userA", USER)
    assert a1_again is a1  # reused, not rebuilt
    assert len(created) == 1


async def test_distinct_sources_get_distinct_agents(tmp_path):
    pool, created = make_pool(str(tmp_path))

    a = await pool.get_agent("userA", USER)
    b = await pool.get_agent("userB", USER)

    assert a is not b
    assert len(created) == 2


async def test_lazy_no_agent_for_silent_source(tmp_path):
    pool, created = make_pool(str(tmp_path))

    await pool.get_agent("userA", USER)
    # userB never asked → never built
    assert created == [os.path.join(str(tmp_path), "sources", "userA")]
    assert "userB" not in pool._agents


async def test_per_source_storage_dir_under_base(tmp_path):
    pool, created = make_pool(str(tmp_path))

    await pool.get_agent("userA", USER)

    expected = os.path.join(str(tmp_path), "sources", "userA")
    assert created == [expected]
    assert os.path.isdir(expected)  # directory is created


async def test_requester_agent_source_pooled_same_as_user(tmp_path):
    """A requester agent (SUBAGENT, keyed by agentInstanceId) pools the same way a
    human user does — the pool is generic over the source id."""
    pool, created = make_pool(str(tmp_path))

    a = await pool.get_agent("agent-instance-1", SUBAGENT)
    a_again = await pool.get_agent("agent-instance-1", SUBAGENT)

    assert a_again is a
    assert created == [os.path.join(str(tmp_path), "sources", "agent-instance-1")]


async def test_concurrent_first_turns_same_source_build_one_agent(tmp_path):
    """Two concurrent first-turns for the SAME source must not build two agents
    (double-checked creation lock)."""
    call_count = {"n": 0}

    async def slow_create(source_storage_dir):
        call_count["n"] += 1
        await asyncio.sleep(0.05)  # widen the race window
        return object()

    pool = StreamingAgentPool(create_agent=slow_create, base_storage_dir=str(tmp_path))

    a, b = await asyncio.gather(pool.get_agent("userA", USER), pool.get_agent("userA", USER))

    assert a is b  # same cached agent
    assert call_count["n"] == 1  # built exactly once despite the race


async def test_concurrent_distinct_sources_build_in_parallel(tmp_path):
    pool, created = make_pool(str(tmp_path))

    results = await asyncio.gather(*[pool.get_agent(f"user{i}", USER) for i in range(5)])

    assert len({id(r) for r in results}) == 5  # 5 distinct agents
    assert len(created) == 5


def test_safe_dir_name_sanitizes_unsafe_chars():
    assert _safe_dir_name("a/b:c\\d") == "a_b_c_d"
    assert _safe_dir_name("") == "unknown"
    # long ids are truncated
    assert len(_safe_dir_name("x" * 500)) == 128


def test_source_field_names_the_id_by_type():
    assert _source_field(USER) == "userId"
    assert _source_field(SUBAGENT) == "agentInstanceId"


# ---- idle-TTL eviction --------------------------------------------------------


def make_pool_with_clock(base_dir, ttl, monkeypatch):
    """Pool with a controllable monotonic clock and a settable idle TTL."""
    created = []
    clock = {"now": 1000.0}

    monkeypatch.setattr(
        "agent_builder_sdk.server.streaming_agent_pool.time.monotonic",
        lambda: clock["now"],
    )

    async def create_agent(source_storage_dir):
        created.append(source_storage_dir)
        return object()

    pool = StreamingAgentPool(
        create_agent=create_agent, base_storage_dir=base_dir, idle_ttl_seconds=ttl
    )
    return pool, created, clock


async def test_idle_agent_evicted_after_ttl(tmp_path, monkeypatch):
    pool, created, clock = make_pool_with_clock(str(tmp_path), ttl=100, monkeypatch=monkeypatch)

    a1 = await pool.get_agent("userA", USER)
    assert "userA" in pool._agents

    # advance past TTL, then a different source's turn triggers the lazy sweep
    clock["now"] += 101
    await pool.get_agent("userB", USER)
    assert "userA" not in pool._agents  # evicted
    assert "userB" in pool._agents

    # userA returns → a NEW agent is built (rebuild is safe; durable state is shared)
    a2 = await pool.get_agent("userA", USER)
    assert a2 is not a1
    assert created.count(os.path.join(str(tmp_path), "sources", "userA")) == 2


async def test_active_source_not_evicted(tmp_path, monkeypatch):
    pool, _created, clock = make_pool_with_clock(str(tmp_path), ttl=100, monkeypatch=monkeypatch)

    a1 = await pool.get_agent("userA", USER)
    # keep touching userA within the TTL window; it must survive sweeps
    for _ in range(5):
        clock["now"] += 50  # < ttl since last use each time
        got = await pool.get_agent("userA", USER)
        assert got is a1  # same cached agent, never evicted/rebuilt


async def test_in_flight_lease_blocks_eviction_mid_turn(tmp_path, monkeypatch):
    """A source with an active lease (in-flight streaming turn) is NEVER evicted, even if its
    timestamp is far past the TTL — eviction mid-stream would let a concurrent same-source turn
    build a second agent, breaking the one-invocation-per-source guarantee."""
    pool, _created, clock = make_pool_with_clock(str(tmp_path), ttl=100, monkeypatch=monkeypatch)

    a1 = await pool.get_agent("userA", USER)

    async with pool.lease("userA"):
        clock["now"] += 10_000  # userA is now WAY past the TTL, but a turn is in-flight
        await pool.get_agent("userB", USER)  # triggers a sweep
        assert "userA" in pool._agents  # not evicted — lease held
        assert pool._agents["userA"] is a1

    # lease released + idle time refreshed to now; still present immediately after
    assert "userA" in pool._agents
    assert pool._in_flight.get("userA", 0) == 0


async def test_lease_release_refreshes_idle_time(tmp_path, monkeypatch):
    """Releasing a lease refreshes last-used so the TTL is measured from the turn's END,
    not its start (a long turn shouldn't be instantly evictable when it finishes)."""
    pool, _created, clock = make_pool_with_clock(str(tmp_path), ttl=100, monkeypatch=monkeypatch)

    await pool.get_agent("userA", USER)
    async with pool.lease("userA"):
        clock["now"] += 500  # long turn, well past TTL
    # right after release: within TTL of the release instant → survives a sweep
    clock["now"] += 50
    await pool.get_agent("userB", USER)
    assert "userA" in pool._agents


async def test_lease_is_reentrant_counted(tmp_path, monkeypatch):
    """Overlapping leases for the same source are reference-counted; the source stays in-flight
    until the LAST lease releases."""
    pool, _created, clock = make_pool_with_clock(str(tmp_path), ttl=100, monkeypatch=monkeypatch)
    await pool.get_agent("userA", USER)

    async with pool.lease("userA"):
        async with pool.lease("userA"):
            assert pool._in_flight["userA"] == 2
        assert pool._in_flight["userA"] == 1  # inner released, still in-flight
    assert pool._in_flight.get("userA", 0) == 0  # both released


def test_non_positive_ttl_rejected():
    """idle_ttl_seconds <= 0 would evict every sweep (defeating pooling) — reject at construction."""
    import pytest

    async def create(_):
        return object()

    for bad in (0, -1, -0.5):
        with pytest.raises(ValueError, match="idle_ttl_seconds must be positive"):
            StreamingAgentPool(create_agent=create, base_storage_dir="/tmp/x", idle_ttl_seconds=bad)
