# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the client-side SSE reader."""

import asyncio
import json
import threading

import pytest

from agent_builder_sdk.streaming.sse_reader import (
    async_iter_from_sync,
    iter_frames,
    parse_sse_events,
)


def _sse(*objs):
    """Serialize objects as SSE data events (bytes)."""
    return "".join(f"data: {json.dumps(o)}\n\n" for o in objs).encode("utf-8")


def test_single_event():
    frames = list(parse_sse_events([_sse({"kind": "task", "a": 1})]))
    assert frames == [{"kind": "task", "a": 1}]


def test_multiple_events_in_one_chunk():
    frames = list(parse_sse_events([_sse({"i": 1}, {"i": 2}, {"i": 3})]))
    assert [f["i"] for f in frames] == [1, 2, 3]


def test_event_split_across_chunks():
    raw = _sse({"kind": "status-update", "hello": "world"})
    # Split the byte stream at an arbitrary boundary mid-object.
    mid = len(raw) // 2
    chunks = [raw[:mid], raw[mid:]]
    frames = list(parse_sse_events(chunks))
    assert frames == [{"kind": "status-update", "hello": "world"}]


def test_multiline_data_joined_with_newline():
    # Two data: lines within one event join with \n, then must parse as one JSON string.
    payload = json.dumps({"text": "line1\nline2"})
    part1, part2 = payload.split("\\n", 1)
    raw = f"data: {part1}\\n\ndata: {part2}\n\n".encode("utf-8")
    # Simpler: emit a JSON object spanning two data lines.
    raw = b'data: {"a":\ndata: 1}\n\n'
    frames = list(parse_sse_events([raw]))
    assert frames == [{"a": 1}]


def test_comment_and_other_fields_ignored():
    raw = b': this is a comment\nevent: message\nid: 5\ndata: {"ok": true}\n\n'
    frames = list(parse_sse_events([raw]))
    assert frames == [{"ok": True}]


def test_trailing_event_without_blank_line_flushed():
    raw = b'data: {"final": true}'  # no trailing \n\n
    frames = list(parse_sse_events([raw]))
    assert frames == [{"final": True}]


def test_unparseable_payload_skipped():
    raw = b'data: not-json\n\ndata: {"ok": 1}\n\n'
    frames = list(parse_sse_events([raw]))
    assert frames == [{"ok": 1}]


def test_multibyte_char_split_at_every_boundary():
    # Raw UTF-8 on the wire (ensure_ascii=False) so multibyte chars are real multi-byte sequences,
    # including a 4-byte emoji. Splitting at ANY byte offset must still decode correctly — a
    # per-chunk bytes.decode would raise UnicodeDecodeError whenever a split lands mid-character.
    obj = {"data": "これは日本語のテストです 🎉"}
    raw = ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
    for i in range(1, len(raw)):
        frames = list(parse_sse_events([raw[:i], raw[i:]]))
        assert frames == [obj], f"failed at split offset {i}"


def test_multibyte_char_one_byte_at_a_time():
    obj = {"emoji": "🎉", "jp": "これ"}
    raw = ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
    chunks = [raw[i : i + 1] for i in range(len(raw))]
    frames = list(parse_sse_events(chunks))
    assert frames == [obj]


def test_incomplete_trailing_multibyte_does_not_raise():
    # A complete frame, then a dangling partial multibyte character at EOF (no terminator). The
    # good frame is still delivered and the truncated tail is dropped rather than raising.
    good = ("data: " + json.dumps({"ok": 1}) + "\n\n").encode("utf-8")
    raw = good + b'data: "\xe3\x81'  # truncated mid-character
    frames = list(parse_sse_events([raw]))
    assert frames == [{"ok": 1}]


class _FakeBody:
    """Minimal StreamingBody stand-in with iter_chunks."""

    def __init__(self, data: bytes, chunk_size: int = 8):
        self._data = data
        self._chunk_size = chunk_size

    def iter_chunks(self, chunk_size):
        n = chunk_size or self._chunk_size
        for i in range(0, len(self._data), n):
            yield self._data[i : i + n]


def test_iter_frames_stops_on_final():
    body = _FakeBody(
        _sse({"kind": "status-update", "final": False}, {"final": True}, {"after": "terminal"})
    )
    frames = list(iter_frames(body))
    # Stops right after the final frame; the third frame is not yielded.
    assert frames[-1] == {"final": True}
    assert {"after": "terminal"} not in frames


def test_iter_frames_stops_on_completed_state():
    body = _FakeBody(
        _sse({"status": {"state": "working"}}, {"status": {"state": "completed"}}, {"x": 1})
    )
    frames = list(iter_frames(body))
    assert frames[-1] == {"status": {"state": "completed"}}
    assert len(frames) == 2


def test_iter_frames_stops_on_failed_state():
    body = _FakeBody(_sse({"status": {"state": "failed"}}))
    frames = list(iter_frames(body))
    assert frames == [{"status": {"state": "failed"}}]


def test_iter_frames_stops_on_stream_close_without_final():
    # Neither final nor a terminal state — iterator ends when chunks are exhausted.
    body = _FakeBody(_sse({"status": {"state": "working"}}, {"status": {"state": "working"}}))
    frames = list(iter_frames(body))
    assert len(frames) == 2


def test_iter_frames_read_fallback():
    class _ReadBody:
        def __init__(self, data):
            self._data = data
            self._pos = 0

        def read(self, n):
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
            return chunk

    body = _ReadBody(_sse({"final": True}))
    assert list(iter_frames(body)) == [{"final": True}]


class _ClosableBody(_FakeBody):
    """StreamingBody stand-in that records whether close() was called."""

    def __init__(self, data: bytes, chunk_size: int = 8):
        super().__init__(data, chunk_size)
        self.close_called = False

    def close(self):
        self.close_called = True


def test_iter_frames_closes_body_on_early_terminal():
    # The common path: a terminal frame arrives before the body is drained. The socket must still
    # be closed rather than left for GC.
    body = _ClosableBody(_sse({"final": True}, {"after": "terminal"}))
    frames = list(iter_frames(body))
    assert frames == [{"final": True}]
    assert body.close_called is True


def test_iter_frames_closes_body_on_exhaustion():
    body = _ClosableBody(_sse({"status": {"state": "working"}}))
    list(iter_frames(body))
    assert body.close_called is True


def test_iter_frames_closes_body_when_generator_closed_early():
    # Consumer stops iterating before the terminal (e.g. relay breaks out) — the finally still runs.
    body = _ClosableBody(_sse({"a": 1}, {"b": 2}, {"final": True}))
    gen = iter_frames(body)
    assert next(gen) == {"a": 1}
    gen.close()
    assert body.close_called is True


def test_iter_frames_body_without_close_does_not_raise():
    # A body lacking close() (e.g. a test/read-only stand-in) must not break the reader.
    body = _FakeBody(_sse({"final": True}))
    assert list(iter_frames(body)) == [{"final": True}]


async def test_async_iter_from_sync_yields_in_order():
    def gen():
        yield {"i": 1}
        yield {"i": 2}
        yield {"i": 3}

    out = [f async for f in async_iter_from_sync(gen())]
    assert [f["i"] for f in out] == [1, 2, 3]


async def test_async_iter_from_sync_reraises_producer_exception():
    def gen():
        yield {"i": 1}
        raise ValueError("boom")

    seen = []
    with pytest.raises(ValueError, match="boom"):
        async for f in async_iter_from_sync(gen()):
            seen.append(f)
    assert seen == [{"i": 1}]


async def test_async_iter_from_sync_early_exit_does_not_hang():
    def gen():
        for i in range(1000):
            yield {"i": i}

    out = []
    async for f in async_iter_from_sync(gen()):
        out.append(f)
        if len(out) == 2:
            break
    assert len(out) == 2


async def test_async_iter_from_sync_blocking_producer_does_not_strand_consumer():
    """A producer that blocks forever after a few frames must not hang the consumer's early exit
    (nor, since it runs on a daemon thread, the interpreter/pytest at process exit). Regression for
    the build-hang where the non-daemon producer parked on a closed loop and blocked the atexit join.
    """
    gate = threading.Event()

    def gen():
        yield {"i": 0}
        yield {"i": 1}
        gate.wait()  # block indefinitely; the daemon producer is killed at interpreter exit
        yield {"i": 2}  # never reached

    async def consume_two():
        out = []
        async for f in async_iter_from_sync(gen()):
            out.append(f)
            if len(out) == 2:
                break
        return out

    try:
        # wait_for so a regression fails fast (TimeoutError) instead of hanging the suite.
        out = await asyncio.wait_for(consume_two(), timeout=5)
    finally:
        gate.set()  # release the producer so it exits cleanly, leaving no lingering thread
    assert out == [{"i": 0}, {"i": 1}]
