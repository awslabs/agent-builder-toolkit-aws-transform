# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import re
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest
import requests
from botocore.exceptions import ClientError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from agent_builder_sdk.agentic_framework import common
from agent_builder_sdk.errors import InternalBaseAgentError, UserBaseAgentError
from agent_builder_types import type_defs as abt


@pytest.fixture
def session():
    session = mock.create_autospec(requests.Session, instance=True)
    with mock.patch(
        "agent_builder_sdk.agentic_framework.common.requests.Session"
    ) as session_class:
        session_class.return_value.__enter__.return_value = session
        yield session


@pytest.fixture
def response():
    return mock.create_autospec(requests.Response, instance=True)


@pytest.fixture
def upload_response(response_metadata) -> abt.CreateArtifactUploadUrlResponseTypeDef:
    return abt.CreateArtifactUploadUrlResponseTypeDef(
        artifactId="123",
        s3preSignedUrl="https://test-url.com",
        s3UrlExpiryTimestamp=datetime.now(),
        requestHeaders={"Content-Type": ["application/octet-stream"]},
        ResponseMetadata=response_metadata,
    )


@pytest.fixture
def download_response(response_metadata) -> abt.CreateArtifactDownloadUrlResponseTypeDef:
    artifact_type: abt.ArtifactTypeTypeDef = {"categoryType": "STATE", "fileType": "ZIP"}

    return abt.CreateArtifactDownloadUrlResponseTypeDef(
        artifact=abt.ArtifactTypeDef(
            artifactId="123",
            artifactType=artifact_type,
            artifactCreatedTimestamp=datetime.now(),
            artifactExpiryTimestamp=datetime.now(),
            storedInAtxBucket=True,
        ),
        artifactType=artifact_type,
        artifactLabel="label",
        s3preSignedUrl="https://test-download-url.com",
        s3UrlExpiryTimestamp=datetime.now(),
        requestHeaders={"Content-Type": ["application/octet-stream"]},
        ResponseMetadata=response_metadata,
    )


def test_calculate_digest():
    """Test SHA256 digest calculation with base64 encoding."""
    content = b"test content"
    result = common.calculate_digest(content)

    # Expected base64-encoded SHA256 of "test content"
    expected = "auinVVUgn9bEQVfArtgBbnY/9DWhnPGG92hjFAFD/3I="
    assert result == expected


def test_calculate_digest_empty():
    """Test SHA256 digest of empty content with base64 encoding."""
    content = b""
    result = common.calculate_digest(content)

    # Expected base64-encoded SHA256 of empty string
    expected = "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
    assert result == expected


@mock.patch("agent_builder_sdk.agentic_framework.common.hashlib.sha256")
def test_calculate_digest_error(mock_sha256):
    """Test calculate_digest error handling."""
    mock_sha256.side_effect = Exception("Hash calculation failed")

    with pytest.raises(Exception, match="Hash calculation failed"):
        common.calculate_digest(b"test content")


def test_upload_from_presigned_url_success(session, response, upload_response):
    """Test successful upload using presigned URL."""
    response.status_code = 200
    session.put.return_value = response

    content = b"test content"
    common.upload_from_presigned_url(upload_response, content)

    expected_headers = {"Content-Type": "application/octet-stream"}
    session.put.assert_called_once_with(
        "https://test-url.com",
        data=mock.ANY,
        headers=expected_headers,
        timeout=common._PRESIGNED_UPLOAD_TIMEOUT,
    )
    assert session.put.call_args.kwargs["data"].read() == content  # streamed, not bytes


def test_upload_from_presigned_url_failure(session, response, upload_response):
    """Test upload failure handling."""
    response.status_code = 500
    response.text = "Internal Server Error"
    session.put.return_value = response
    content = b"test content"

    with pytest.raises(InternalBaseAgentError):
        common.upload_from_presigned_url(upload_response, content)


def test_upload_from_presigned_url_connection_error(session, upload_response):
    """Test upload connection error handling."""
    session.put.side_effect = requests.exceptions.ConnectionError("Connection failed")
    content = b"test content"

    with pytest.raises(InternalBaseAgentError):
        common.upload_from_presigned_url(upload_response, content)


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ReadTimeout("read timed out"),
        requests.exceptions.ConnectTimeout("connect timed out"),
        requests.exceptions.ConnectionError("connection failed"),
    ],
)
def test_upload_from_presigned_url_wraps_every_transport_error(exc, session, upload_response):
    """ReadTimeout does not subclass ConnectionError, so it needs catching explicitly.

    Without it the timeout this function now passes would escape as an unhandled
    ReadTimeout -- the very failure the timeout exists to contain.
    """
    session.put.side_effect = exc

    with pytest.raises(InternalBaseAgentError):
        common.upload_from_presigned_url(upload_response, b"test content")


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ReadTimeout("read timed out"),
        requests.exceptions.ConnectTimeout("connect timed out"),
        requests.exceptions.ConnectionError("connection failed"),
    ],
)
def test_download_from_presigned_url_wraps_every_transport_error(
    exc, session, download_response, tmp_path
):
    """Same timeout handling on the download path."""
    session.get.side_effect = exc

    with pytest.raises(InternalBaseAgentError):
        common.download_from_presigned_url(download_response, str(tmp_path / "file.zip"))


def test_upload_read_timeout_is_looser_than_download():
    """An upload waits on S3 to acknowledge the PUT, which outlasts any single read
    while streaming a download, so a shared 60s bound would fail large uploads that
    succeed today."""
    assert common._PRESIGNED_UPLOAD_TIMEOUT[1] > common._PRESIGNED_DOWNLOAD_TIMEOUT[1]
    assert common._PRESIGNED_UPLOAD_TIMEOUT[0] == common._PRESIGNED_DOWNLOAD_TIMEOUT[0]


@pytest.mark.parametrize("method", ["PUT", "GET"])
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_presigned_url_retry_retries_throttles_and_server_errors(method, status):
    """A 503 SlowDown must be retried; the previous bare max_retries=3 never retried one."""
    assert common._PRESIGNED_URL_RETRY.is_retry(method, status) is True
    assert not Retry.from_int(3).is_retry(method, status)


def test_presigned_url_retry_returns_exhausted_response_instead_of_raising():
    """raise_on_status=False keeps S3 error classification working after retries run out.

    With the urllib3 default (True) an exhausted 503 raises RetryError, which is neither
    caught as a ConnectionError nor passed to raise_for_s3_error_response, so callers
    would lose the formatted S3 error they get today.
    """
    assert common._PRESIGNED_URL_RETRY.raise_on_status is False
    assert common._PRESIGNED_URL_RETRY.total == 3
    assert common._PRESIGNED_URL_RETRY.backoff_factor > 0


def test_upload_from_presigned_url_mounts_retry_policy(session, response, upload_response):
    """The retry policy, not a bare int, is what gets mounted for https."""
    response.status_code = 200
    session.put.return_value = response

    common.upload_from_presigned_url(upload_response, b"test content")

    prefix, adapter = session.mount.call_args.args
    assert prefix == "https://"
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries is common._PRESIGNED_URL_RETRY


def test_download_from_presigned_url_mounts_retry_policy(
    session, response, download_response, tmp_path
):
    """The download path shares the upload path's retry policy."""
    response.content = b"downloaded content"
    response.status_code = 200
    session.get.return_value = response

    common.download_from_presigned_url(download_response, str(tmp_path / "file.zip"))

    prefix, adapter = session.mount.call_args.args
    assert prefix == "https://"
    assert adapter.max_retries is common._PRESIGNED_URL_RETRY


# The tests below send real requests through requests/urllib3 to a local HTTP server, so
# retries, body rewinds and timeouts run for real rather than against a mocked Session.

_SLOW_DOWN = (
    503,
    b"<Error><Code>SlowDown</Code><Message>Please reduce your request rate.</Message>"
    b"<RequestId>1</RequestId></Error>",
)


class _FakeS3Handler(BaseHTTPRequestHandler):
    """Answers each complete request with the next (status, body) in server.responses and
    records the (Content-Length header, body) it received in server.received."""

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = bytearray()
        while chunk := self.rfile.read1(min(1 << 16, length - len(body))):
            body += chunk
            time.sleep(self.server.drain_delay)
        if len(body) < length:  # the client gave up mid-body; its retry is a new request
            return
        self.server.received.append((self.headers.get("Content-Length"), bytes(body)))
        status, payload = self.server.responses.pop(0)
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_PUT

    def log_message(self, format, *args):
        pass


@pytest.fixture
def fake_s3(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeS3Handler, bind_and_activate=False)
    # A small receive buffer, so the kernel cannot soak up the slow-drain test's body.
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 16)
    server.server_bind()
    server.server_activate()
    server.responses, server.received, server.drain_delay = [], [], 0
    server.presigned = {
        "s3preSignedUrl": f"http://127.0.0.1:{server.server_port}/artifact",
        "requestHeaders": {},
    }
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    ).start()
    # Presigned URLs are https, so the code mounts its retry adapter for https:// only.
    # Send this plain-http server's traffic through that same adapter.
    monkeypatch.setattr(
        requests.Session, "get_adapter", lambda self, url: self.adapters["https://"]
    )
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("content", [b"artifact bytes", b""], ids=["body", "empty"])
def test_upload_retries_slow_down_and_resends_whole_body(fake_s3, content):
    """A 503 SlowDown is retried, and the retry rewinds and resends the whole body. Every
    attempt carries Content-Length, as S3 requires, including for an empty body."""
    fake_s3.responses = [_SLOW_DOWN, (200, b"")]

    common.upload_from_presigned_url(fake_s3.presigned, content)

    assert fake_s3.received == [(str(len(content)), content)] * 2


def test_download_retries_slow_down(fake_s3, tmp_path):
    fake_s3.responses = [_SLOW_DOWN, (200, b"artifact bytes")]
    destination = tmp_path / "artifact.zip"

    common.download_from_presigned_url(fake_s3.presigned, str(destination))

    assert destination.read_bytes() == b"artifact bytes"
    assert len(fake_s3.received) == 2


def test_upload_connect_timeout_bounds_each_write_not_the_whole_body(fake_s3, monkeypatch):
    """urllib3 sends the request under the connect timeout. The server drains this body too
    slowly for one write of all of it to finish within that timeout, but each small write of
    the streamed body does."""
    monkeypatch.setattr(common, "_PRESIGNED_UPLOAD_TIMEOUT", (0.1, 5))
    fake_s3.drain_delay = 0.001  # at most 64 KiB per millisecond
    fake_s3.responses = [(200, b"")]
    content = bytes(range(256)) * (12 << 12)  # 12 MiB

    common.upload_from_presigned_url(fake_s3.presigned, content)

    intact = fake_s3.received == [(str(len(content)), content)]  # no 12 MiB diff on failure
    assert intact


def test_handle_boto_error():
    """Test boto error handling."""
    error = ClientError(
        error_response={"Error": {"Code": "TestError", "Message": "Test error message"}},
        operation_name="TestOperation",
    )

    with pytest.raises(ClientError):
        common.handle_boto_error(error)


def test_download_from_presigned_url_success(session, response, download_response, tmp_path):
    """Test successful download using presigned URL."""
    response.content = b"downloaded content"
    response.status_code = 200
    session.get.return_value = response

    destination_path = tmp_path / "file.zip"

    common.download_from_presigned_url(download_response, str(destination_path))

    expected_headers = {"Content-Type": "application/octet-stream"}
    session.get.assert_called_once_with(
        "https://test-download-url.com",
        headers=expected_headers,
        timeout=common._PRESIGNED_DOWNLOAD_TIMEOUT,
    )
    assert destination_path.read_bytes() == b"downloaded content"


def test_download_from_presigned_url_connection_error(session, download_response, tmp_path):
    """Test download connection error handling."""
    session.get.side_effect = requests.exceptions.ConnectionError("Connection failed")
    destination_path = tmp_path / "file.zip"

    with pytest.raises(InternalBaseAgentError):
        common.download_from_presigned_url(download_response, str(destination_path))


@mock.patch("agent_builder_sdk.agentic_framework.common.Path")
def test_download_from_presigned_url_file_error(mock_path, response, session, download_response):
    """Test download file write error handling."""
    mock_path.return_value.write_bytes.side_effect = IOError("File write error")

    response.content = b"downloaded content"
    response.status_code = 200
    session.get.return_value = response

    destination_path = "/test/path/file.zip"

    with pytest.raises(IOError):
        common.download_from_presigned_url(download_response, destination_path)


def test_download_from_presigned_url_capital_p_key(session, response, tmp_path):
    """Test download with s3PreSignedUrl (capital P) key for skill downloads."""
    response.content = b"skill content"
    response.status_code = 200
    session.get.return_value = response

    download_response = {
        "s3PreSignedUrl": "https://skill-download-url.com",
        "requestHeaders": {"host": ["s3.amazonaws.com"]},
    }
    destination_path = tmp_path / "skill.zip"

    common.download_from_presigned_url(download_response, str(destination_path))

    session.get.assert_called_once_with(
        "https://skill-download-url.com",
        headers={"host": "s3.amazonaws.com"},
        timeout=common._PRESIGNED_DOWNLOAD_TIMEOUT,
    )
    assert destination_path.read_bytes() == b"skill content"


@mock.patch("agent_builder_sdk.agentic_framework.common.requests.Session")
def test_download_from_presigned_url_missing_both_keys(mock_session_class):
    """Test download fails when neither s3PreSignedUrl nor s3preSignedUrl is present."""
    download_response = {
        "requestHeaders": {"host": ["s3.amazonaws.com"]},
    }
    destination_path = "/test/path/file.zip"

    with pytest.raises(KeyError, match="Neither 's3PreSignedUrl' nor 's3preSignedUrl' found"):
        common.download_from_presigned_url(download_response, destination_path)


@pytest.mark.parametrize(
    ["is_managed_bucket", "expected_error"],
    [(True, InternalBaseAgentError), (False, UserBaseAgentError)],
)
def test_raise_for_s3_error_response_access_denied(is_managed_bucket, expected_error):
    response_text = """
    <Error>
        <Code>AccessDenied</Code>
        <RequestId>123</RequestId>
        <Message>message</Message>
    </Error>
    """
    expected_message = re.escape(
        "message (Service: Amazon S3; Status Code: 400; "
        "Error Code: AccessDenied; Request ID: 123)"
    )

    with pytest.raises(expected_error, match=expected_message):
        common.raise_for_s3_error_response(400, response_text, is_managed_bucket)


@pytest.mark.parametrize("is_managed_bucket", [True, False])
def test_raise_for_s3_error_response_no_error_code(is_managed_bucket):
    response_text = "<Error></Error>"
    expected_message = re.escape(
        "(Service: Amazon S3; Status Code: 400; Error Code: None; Request ID: None)"
    )

    with pytest.raises(InternalBaseAgentError, match=expected_message):
        common.raise_for_s3_error_response(400, response_text, is_managed_bucket)


@pytest.mark.parametrize(
    "response_text",
    (
        """
        <NotError>
            <RequestId>123</RequestId>
            <Message>message</Message>
        </NotError>
        """,
        """
        <Error>
            <Code>InvalidRequest</Code>
            <RequestId>123</RequestId>
            <Message>message</Message>
        </Error>
        """,
        """
        <Error>
            <Code>InvalidRequest</Code>
            <RequestId>123</RequestId>
            <Message>message</Message>
        """,
    ),
)
def test_raise_for_s3_error_response_internal_error(response_text):
    with pytest.raises(InternalBaseAgentError, match="Unexpected 400 S3 error"):
        common.raise_for_s3_error_response(400, response_text, False)


@pytest.mark.parametrize(
    "response_text",
    (
        """
        <NotError>
            <RequestId>123</RequestId>
            <Message>message</Message>
        </NotError>
        """,
        """
        <Error>
            <Code>InvalidRequest</Code>
            <RequestId>123</RequestId>
            <Message>message</Message>
        """,
    ),
)
def test_raise_for_s3_error_response_internal_error_managed_bucket(response_text):
    with pytest.raises(InternalBaseAgentError, match="Unexpected 400 S3 error"):
        common.raise_for_s3_error_response(400, response_text, True)
