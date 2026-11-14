# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for SuggestionsManager.

Two modes:
- Default (message/send, served by the shared singleton agent): a plain shared holder. Must
  work across the asyncio.to_thread boundary (write in a worker thread, read in the request task).
- Per-turn scope (concurrent streaming): begin_turn_scope() binds a turn-local holder so
  concurrent inline turns don't clobber each other or a concurrent message/send turn.
"""

import asyncio

from agent_builder_sdk.util.suggestions_manager import (
    SuggestionsManager,
    add_suggestions,
    begin_turn_scope,
    clear_suggestions,
    get_and_consume_suggestions,
)


def test_add_then_consume_once():
    mgr = SuggestionsManager()
    mgr.add_suggestions(["a", "b"])
    assert mgr.get_and_consume_suggestions() == ["a", "b"]
    assert mgr.get_and_consume_suggestions() is None  # one-time use


def test_consume_without_add_returns_none():
    assert SuggestionsManager().get_and_consume_suggestions() is None


def test_clear_resets():
    mgr = SuggestionsManager()
    mgr.add_suggestions(["x"])
    mgr.clear_suggestions()
    assert mgr.get_and_consume_suggestions() is None


def test_module_level_api_roundtrip():
    clear_suggestions()
    add_suggestions(["one"])
    assert get_and_consume_suggestions() == ["one"]
    assert get_and_consume_suggestions() is None


async def test_survives_to_thread_boundary_default_path():
    """REGRESSION GUARD for the message/send path: the producer runs inside asyncio.to_thread
    (a copied context / worker thread) and the consumer runs in the request task. A plain
    shared holder must carry the suggestion across that boundary — a ContextVar would not.
    This is the exact break the ContextVar-only refactor introduced."""
    mgr = SuggestionsManager()

    def worker():  # runs in a thread via to_thread (fresh copied context)
        mgr.add_suggestions(["from-worker"])

    await asyncio.to_thread(worker)
    # consumer is back on the event-loop task — must still see it
    assert mgr.get_and_consume_suggestions() == ["from-worker"]


async def test_turn_scope_isolates_concurrent_turns():
    """With begin_turn_scope() (streaming), two concurrent turns must not see each other's
    suggestions."""
    mgr = SuggestionsManager()
    seen: dict[str, list[str] | None] = {}

    async def turn(name: str, chips: list[str], settle: float):
        mgr.begin_turn_scope()
        mgr.add_suggestions(chips)
        await asyncio.sleep(settle)
        seen[name] = mgr.get_and_consume_suggestions()

    await asyncio.gather(
        turn("A", ["a1", "a2"], 0.05),
        turn("B", ["b1"], 0.01),
    )
    assert seen["A"] == ["a1", "a2"]
    assert seen["B"] == ["b1"]


async def test_scoped_turn_does_not_pollute_shared_holder():
    """A streaming turn that opens a scope must NOT leak into the shared holder that a
    concurrent message/send turn consumes."""
    mgr = SuggestionsManager()

    async def scoped_turn():
        mgr.begin_turn_scope()
        mgr.add_suggestions(["streaming-only"])
        # consume within the scope
        return mgr.get_and_consume_suggestions()

    async def message_send_turn():
        # never opens a scope → shared holder; must see nothing from the scoped turn
        await asyncio.sleep(0.02)
        return mgr.get_and_consume_suggestions()

    scoped, message_send = await asyncio.gather(scoped_turn(), message_send_turn())
    assert scoped == ["streaming-only"]
    assert message_send is None  # shared holder untouched by the scoped turn


def test_module_begin_turn_scope_binds_scope():
    """The module-level begin_turn_scope() opens a scope on the global manager (smoke)."""
    clear_suggestions()
    begin_turn_scope()
    add_suggestions(["scoped"])
    assert get_and_consume_suggestions() == ["scoped"]
