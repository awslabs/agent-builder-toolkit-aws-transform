# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Client-side SSE reader for the ConverseStream A2A frame stream.

The caller of ``ConverseStream`` receives a ``text/event-stream`` body (a botocore
``StreamingBody``) whose ``data:`` lines are bare A2A frame objects. This module decodes that byte
stream into frame dicts. It is deliberately dependency-free — the SSE framing is simple enough that
a hand-written parser is smaller and more testable than pulling in an SSE library, and raw A2A
frames are plain dicts, so ``json`` is all that's needed.

Three layers, separated so the tricky parts are unit-testable without any I/O:
- ``parse_sse_events`` — pure: bytes chunks -> frame dicts (handles partial lines, multi-line
  ``data:``, blank-line dispatch, close flush).
- ``iter_frames`` — pumps a ``StreamingBody`` through the parser, stopping at end-of-turn.
- ``async_iter_from_sync`` — bridges the blocking sync iterator to an async generator via a thread
  + queue (a blocking ``StreamingBody`` read cannot be awaited directly).
"""

import asyncio
import codecs
import json
import logging
import queue
import threading
from typing import Any, AsyncIterator, Iterable, Iterator

from agent_builder_sdk.streaming.a2a_frame_utils import A2AFrame, is_end_of_turn

logger = logging.getLogger(__name__)

_DEFAULT_CHUNK_SIZE = 1024


def parse_sse_events(chunks: Iterable[bytes]) -> Iterator[A2AFrame]:
    """Decode a stream of SSE byte chunks into A2A frame dicts (pure, no I/O).

    SSE framing: lines split on ``\\n``; each ``data:`` line contributes its payload (one leading
    space after the colon stripped); consecutive ``data:`` lines within one event join with
    ``\\n``; a blank line dispatches the accumulated event. ``event:`` / ``id:`` / comment (``:``)
    lines are ignored. Byte chunks are arbitrary-sized (not line- or character-aligned), so an
    incomplete trailing line is buffered across chunks, and a multibyte UTF-8 character split across
    a chunk boundary is held by an incremental decoder until its bytes are complete (a per-chunk
    ``bytes.decode`` would raise ``UnicodeDecodeError`` on the split). On exhaustion, any complete
    buffered event is flushed. A data buffer that fails to parse as JSON is logged and skipped
    rather than raising.
    """
    decoder = codecs.getincrementaldecoder("utf-8")()
    line_buf = ""  # incomplete trailing line carried across chunks
    data_parts: list[str] = []  # accumulated `data:` payloads for the current event

    def _dispatch() -> Iterator[A2AFrame]:
        if not data_parts:
            return
        payload = "\n".join(data_parts)
        data_parts.clear()
        payload = payload.strip()
        if not payload:
            return
        try:
            frame = json.loads(payload)
        except (ValueError, TypeError):
            logger.warning("Skipping unparseable SSE data payload: %r", payload[:200])
            return
        if isinstance(frame, dict):
            yield frame

    for chunk in chunks:
        text = decoder.decode(chunk) if isinstance(chunk, (bytes, bytearray)) else chunk
        line_buf += text
        while "\n" in line_buf:
            line, line_buf = line_buf.split("\n", 1)
            line = line.rstrip("\r")
            if line == "":
                yield from _dispatch()
            elif line.startswith(":"):
                continue  # comment
            elif line.startswith("data:"):
                data_parts.append(line[len("data:") :].lstrip(" "))
            # event: / id: / other fields are not used by this consumer

    # Flush any bytes the decoder still holds for an incomplete trailing multibyte sequence. A clean
    # stream ends on a character boundary (returns ""); truly truncated trailing bytes raise, which
    # we log and drop rather than aborting the whole stream (consistent with the JSON-skip above).
    try:
        line_buf += decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        logger.warning("Discarding incomplete trailing bytes at end of SSE stream")

    # Flush a final event with no trailing blank line, plus any complete buffered line.
    if line_buf:
        line = line_buf.rstrip("\r")
        if line.startswith("data:"):
            data_parts.append(line[len("data:") :].lstrip(" "))
    yield from _dispatch()


def _read_chunks(body: Any, chunk_size: int) -> Iterator[bytes]:
    """Yield byte chunks from a botocore StreamingBody (or any read/iter_chunks-capable body)."""
    iter_chunks = getattr(body, "iter_chunks", None)
    if callable(iter_chunks):
        yield from iter_chunks(chunk_size)
        return
    # Fallback: plain read loop.
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            return
        yield chunk


def iter_frames(body: Any, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> Iterator[A2AFrame]:
    """Decode a StreamingBody into A2A frames, stopping at end-of-turn.

    Pumps the body's byte chunks through ``parse_sse_events`` and yields each frame. Ends when a
    frame is end-of-turn (``final: true`` or a terminal state) — that frame is yielded, then the
    iterator returns. Natural stream close (chunks exhausted) also ends the iterator, covering the
    A2A-v1.0 case where neither ``final`` nor a terminal state is guaranteed.

    The ``StreamingBody`` wraps a pooled HTTP socket, so it is closed on every exit path (early
    terminal, exhaustion, or the generator being closed early) via ``finally`` — otherwise the
    socket leaks until GC and slowly drains botocore's connection pool / file descriptors under
    concurrent long-lived streams. Closing is best-effort: a missing/failing ``close`` never masks
    the frames already produced.
    """
    try:
        for frame in parse_sse_events(_read_chunks(body, chunk_size)):
            yield frame
            if is_end_of_turn(frame):
                return
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.debug("Error closing StreamingBody", exc_info=True)


class _StreamEnd:
    """Sentinel marking normal completion of the producer thread."""


async def async_iter_from_sync(
    sync_iter: Iterator[A2AFrame], queue_maxsize: int = 32, poll_interval: float = 0.005
) -> AsyncIterator[A2AFrame]:
    """Adapt a blocking sync frame iterator to an async generator via a daemon thread + queue.

    A botocore ``StreamingBody`` read is blocking and cannot be awaited, so ``iter_frames`` must run
    off the event loop. A producer thread drains ``sync_iter`` into a bounded, thread-safe
    ``queue.Queue`` (backpressure) and this async generator polls it. A sentinel marks normal end; an
    exception from the thread is captured and re-raised on the consumer side.

    The producer is a **daemon** thread (not ``asyncio.to_thread``, whose non-daemon pool thread would
    block the interpreter's atexit join if it got stuck on a read), and the hand-off is a plain
    ``queue.Queue`` rather than an ``asyncio.Queue`` — so a stuck or abandoned producer can never keep
    the process from exiting, and neither side ever blocks on the event loop.
    """
    handoff: "queue.Queue[Any]" = queue.Queue(maxsize=queue_maxsize)
    stop = threading.Event()

    def _put(item: Any) -> None:
        # Wait for room, but wake every poll_interval so an early consumer exit is honored promptly.
        while not stop.is_set():
            try:
                handoff.put(item, timeout=poll_interval)
                return
            except queue.Full:
                continue

    def _produce() -> None:
        try:
            for frame in sync_iter:
                if stop.is_set():
                    return
                _put(frame)
                if stop.is_set():
                    return
            _put(_StreamEnd)
        except Exception as exc:  # noqa: BLE001 - surfaced to the consumer below
            _put(exc)

    producer = threading.Thread(target=_produce, name="sse-frame-producer", daemon=True)
    producer.start()
    try:
        while True:
            try:
                item = handoff.get_nowait()
            except queue.Empty:
                # Safety net: if the producer died without a terminator (shouldn't happen), don't
                # poll forever. Normal end/error always enqueues _StreamEnd/the exception. The
                # producer can enqueue its last frames and exit between the get above and this
                # check, so drain the queue before giving up.
                if not producer.is_alive():
                    if handoff.empty():
                        return
                    continue
                await asyncio.sleep(poll_interval)
                continue
            if item is _StreamEnd:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        stop.set()
