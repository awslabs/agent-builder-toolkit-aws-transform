# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Streamed presigned transfers, run through requests/urllib3 against a loopback server."""

import os
import stat
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import pytest
import requests
from urllib3.response import HTTPResponse

from agent_builder_sdk.agentic_framework import common
from agent_builder_sdk.errors import InternalBaseAgentError

_SLOW_DOWN = (503, b"<Error><Code>SlowDown</Code><RequestId>1</RequestId></Error>")
_NO_SUCH_KEY = (404, b"<Error><Code>NoSuchKey</Code><RequestId>1</RequestId></Error>")


class _LoopbackS3(ThreadingHTTPServer):
    """Answers each request with the next (status, body) in ``responses`` and records the
    (Content-Length, Transfer-Encoding, body) of each request in ``received``."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.responses: list[tuple[int, bytes]] = []
        self.received: list[tuple[Optional[str], Optional[str], bytes]] = []
        self.truncate_response_to: Optional[int] = None  # body bytes sent before closing
        self.send_content_length = True  # False: the body ends when the connection closes
        self.presigned: dict[str, Any] = {
            "s3preSignedUrl": f"http://127.0.0.1:{self.server_port}/artifact",
            "requestHeaders": {},
        }


class _Handler(BaseHTTPRequestHandler):
    server: _LoopbackS3

    def do_PUT(self) -> None:
        length = self.headers.get("Content-Length")
        body = self.rfile.read(int(length or 0))
        self.server.received.append((length, self.headers.get("Transfer-Encoding"), body))
        status, payload = self.server.responses.pop(0)
        self.send_response(status)
        if self.server.send_content_length:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload[: self.server.truncate_response_to])

    do_GET = do_PUT

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[_LoopbackS3]:
    server = _LoopbackS3()
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    ).start()
    # The code mounts its retry adapter for https:// only; send this http traffic through it.
    monkeypatch.setattr(
        requests.Session, "get_adapter", lambda self, url: self.adapters["https://"]
    )
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        common, "_PRESIGNED_URL_RETRY", common._PRESIGNED_URL_RETRY.new(backoff_factor=0)
    )


@pytest.mark.parametrize("size", [0, 1, 3 * common._STREAM_BLOCK_BYTES + 7])
def test_calculate_file_digest_matches_calculate_digest(tmp_path: Path, size: int) -> None:
    content = os.urandom(size)
    (tmp_path / "f").write_bytes(content)

    assert common.calculate_file_digest(str(tmp_path / "f")) == common.calculate_digest(content)


def test_upload_file_resends_the_whole_file_after_a_throttle(
    s3: _LoopbackS3, tmp_path: Path, fast_backoff: None
) -> None:
    content = os.urandom(common._STREAM_BLOCK_BYTES + 3)
    (tmp_path / "f").write_bytes(content)
    s3.responses = [_SLOW_DOWN, (200, b"")]

    common.upload_file_to_presigned_url(s3.presigned, str(tmp_path / "f"))

    assert s3.received == [(str(len(content)), None, content)] * 2


def test_upload_of_an_empty_file_sends_content_length_not_chunked(
    s3: _LoopbackS3, tmp_path: Path
) -> None:
    (tmp_path / "f").write_bytes(b"")
    s3.responses = [(200, b"")]

    common.upload_file_to_presigned_url(s3.presigned, str(tmp_path / "f"))

    assert s3.received == [("0", None, b"")]


def test_upload_file_raises_the_s3_error(s3: _LoopbackS3, tmp_path: Path) -> None:
    (tmp_path / "f").write_bytes(b"x")
    s3.responses = [(403, b"<Error><Code>AccessDenied</Code><RequestId>1</RequestId></Error>")]

    with pytest.raises(InternalBaseAgentError, match="AccessDenied"):
        common.upload_file_to_presigned_url(s3.presigned, str(tmp_path / "f"))


def test_download_streams_a_multi_block_body(s3: _LoopbackS3, tmp_path: Path) -> None:
    content = os.urandom(2 * common._STREAM_BLOCK_BYTES + 5)
    s3.responses = [(200, content)]

    common.download_from_presigned_url(s3.presigned, str(tmp_path / "new" / "f.zip"))

    assert (tmp_path / "new" / "f.zip").read_bytes() == content
    assert os.listdir(tmp_path / "new") == ["f.zip"]


@pytest.mark.parametrize(
    ("urllib3_enforces_length", "message"),
    [(True, "connection error"), (False, "incomplete body")],
    ids=["urllib3-2", "urllib3-1"],
)
def test_a_cut_download_keeps_the_old_file(
    s3: _LoopbackS3,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    urllib3_enforces_length: bool,
    message: str,
) -> None:
    """urllib3 2.x raises for a body cut short of its Content-Length; 1.x returns it as a
    success. Either way the download fails and the destination keeps its old bytes."""
    monkeypatch.setattr(
        HTTPResponse,
        "enforce_content_length",
        property(lambda self: urllib3_enforces_length, lambda self, value: None),
        raising=False,  # urllib3 sets it per instance; the property overrides that
    )
    destination = tmp_path / "f.zip"
    destination.write_bytes(b"old")
    s3.responses = [(200, b"artifact bytes")]
    s3.truncate_response_to = 7

    with pytest.raises(InternalBaseAgentError, match=f"Artifact download failed: {message}"):
        common.download_from_presigned_url(s3.presigned, str(destination))

    assert destination.read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["f.zip"]


def test_an_s3_error_keeps_the_old_file(s3: _LoopbackS3, tmp_path: Path) -> None:
    destination = tmp_path / "f.zip"
    destination.write_bytes(b"old")
    s3.responses = [_NO_SUCH_KEY]

    with pytest.raises(InternalBaseAgentError, match="NoSuchKey"):
        common.download_from_presigned_url(s3.presigned, str(destination))

    assert destination.read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["f.zip"]


@pytest.mark.parametrize("send_content_length", [True, False])
@pytest.mark.parametrize("size", [0, 10])
def test_a_download_up_to_the_bound_is_written(
    s3: _LoopbackS3,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    send_content_length: bool,
) -> None:
    monkeypatch.setattr(common, "_MAX_DOWNLOAD_BYTES", 10)
    s3.responses = [(200, b"x" * size)]
    s3.send_content_length = send_content_length
    destination = tmp_path / "f.zip"

    common.download_from_presigned_url(s3.presigned, str(destination))

    assert destination.read_bytes() == b"x" * size


def test_a_declared_length_over_the_bound_fails_before_the_body_is_read(
    s3: _LoopbackS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(common, "_MAX_DOWNLOAD_BYTES", 10)
    s3.responses = [(200, b"x" * 11)]
    destination = tmp_path / "new" / "f.zip"

    with pytest.raises(InternalBaseAgentError, match="body of 11 bytes exceeds 10 bytes"):
        common.download_from_presigned_url(s3.presigned, str(destination))

    assert not destination.parent.exists()  # nothing was written, not even the directory


def test_a_body_without_a_length_fails_once_past_the_bound(
    s3: _LoopbackS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(common, "_MAX_DOWNLOAD_BYTES", 10)
    s3.responses = [(200, b"x" * 11)]
    s3.send_content_length = False

    with pytest.raises(InternalBaseAgentError, match="body exceeds 10 bytes"):
        common.download_from_presigned_url(s3.presigned, str(tmp_path / "f.zip"))

    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("target_exists", [True, False])
def test_a_symlinked_destination_is_refused(
    s3: _LoopbackS3, tmp_path: Path, target_exists: bool
) -> None:
    target = tmp_path / "target"
    if target_exists:
        target.write_bytes(b"old")
    link = tmp_path / "link.zip"
    link.symlink_to(target)
    s3.responses = [(200, b"new")]

    with pytest.raises(ValueError, match="is a symlink"):
        common.download_from_presigned_url(s3.presigned, str(link))

    assert s3.received == []
    assert link.is_symlink()
    expected = ["link.zip", "target"] if target_exists else ["link.zip"]
    assert sorted(os.listdir(tmp_path)) == expected


def test_a_new_file_gets_the_umask_mode(s3: _LoopbackS3, tmp_path: Path) -> None:
    s3.responses = [(200, b"new")]
    umask = os.umask(0o027)
    try:
        common.download_from_presigned_url(s3.presigned, str(tmp_path / "f.zip"))
    finally:
        os.umask(umask)

    assert stat.S_IMODE((tmp_path / "f.zip").stat().st_mode) == 0o640


@pytest.mark.parametrize("mode", [0o600, 0o640])
def test_an_existing_file_keeps_its_mode(s3: _LoopbackS3, tmp_path: Path, mode: int) -> None:
    """Checkpoint restore downloads into an open NamedTemporaryFile, which is mode 0600."""
    s3.responses = [(200, b"new")]
    with tempfile.NamedTemporaryFile(dir=tmp_path, suffix=".zip") as temp:
        os.chmod(temp.name, mode)
        common.download_from_presigned_url(s3.presigned, temp.name)

        assert Path(temp.name).read_bytes() == b"new"
        assert stat.S_IMODE(os.stat(temp.name).st_mode) == mode
    assert os.listdir(tmp_path) == []


def test_a_destination_name_near_name_max_works(s3: _LoopbackS3, tmp_path: Path) -> None:
    """The temp file is not named after the destination, so a long name still fits."""
    s3.responses = [(200, b"data")]
    destination = tmp_path / ("a" * 251 + ".csv")

    common.download_from_presigned_url(s3.presigned, str(destination))

    assert destination.read_bytes() == b"data"


def test_an_interrupted_write_leaves_no_temp_file(tmp_path: Path) -> None:
    destination = tmp_path / "f.zip"
    destination.write_bytes(b"old")

    def blocks() -> Iterator[bytes]:
        yield b"partial"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        common._write_file_atomically(blocks(), str(destination))

    assert destination.read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["f.zip"]


def test_two_writes_to_one_path_at_once_each_leave_a_whole_file(tmp_path: Path) -> None:
    """The second write starts and ends while the first is part way through."""
    destination = str(tmp_path / "f.zip")

    def first() -> Iterator[bytes]:
        yield b"first "
        common._write_file_atomically([b"second"], destination)
        assert Path(destination).read_bytes() == b"second"
        yield b"write"

    common._write_file_atomically(first(), destination)

    assert Path(destination).read_bytes() == b"first write"
    assert os.listdir(tmp_path) == ["f.zip"]
