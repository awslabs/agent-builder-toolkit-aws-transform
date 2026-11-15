# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Common utilities for agentic framework.
"""

import base64
import contextlib
import hashlib
import logging
import os
import stat
import uuid
from dataclasses import dataclass
from typing import BinaryIO, Iterable, Iterator, Optional, Union, cast
from xml.etree import ElementTree

import requests
from botocore.exceptions import ClientError
from defusedxml import ElementTree as DefusedElementTree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from agent_builder_sdk.errors import InternalBaseAgentError, UserBaseAgentError
from agent_builder_types.type_defs import (
    CreateArtifactDownloadUrlResponseTypeDef,
    CreateArtifactUploadUrlResponseTypeDef,
)

logger = logging.getLogger(__name__)

_STREAM_BLOCK_BYTES = 1 << 20

# S3 takes at most 5 GiB in a single PUT, which is how an artifact is uploaded through its
# presigned URL, so a longer download body is not an artifact. The bound keeps a faulty
# endpoint from filling the disk.
_MAX_DOWNLOAD_BYTES = 5 << 30

# S3 signals a throttle with 503 SlowDown, which urllib3's default Retry does NOT retry
# (its default status_forcelist is empty), so the transfer used to fail on the first
# throttle. PUT and GET are already in the default allowed_methods, and both are
# idempotent here. raise_on_status=False makes an exhausted retry return the final
# response rather than raising RetryError, so raise_for_s3_error_response still
# classifies the failure exactly as it does today.
_PRESIGNED_URL_RETRY = Retry(
    total=3,
    status_forcelist=(429, 500, 502, 503, 504),
    backoff_factor=0.5,
    raise_on_status=False,
)

# (connect, read) seconds. requests applies no timeout by default, so a wedged socket
# would otherwise block the caller forever. The upload read timeout is the wait for S3 to
# acknowledge a PUT after the body has been sent, which for a large artifact runs longer
# than any single read while streaming a download, so it is not held to the same bound.
_PRESIGNED_UPLOAD_TIMEOUT = (5, 300)
_PRESIGNED_DOWNLOAD_TIMEOUT = (5, 60)

# ConnectTimeout subclasses ConnectionError, but ReadTimeout does not, so catching only
# ConnectionError would let the timeouts above escape as an unhandled ReadTimeout.
# ChunkedEncodingError subclasses neither: requests raises it when urllib3 reports that
# the connection dropped while the response body was read. urllib3 2.x reports a body cut
# short of its Content-Length that way; 1.x returns the short body as a success, which is
# why download_from_presigned_url checks the length itself.
_TRANSPORT_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@dataclass
class InternalServerException(Exception):
    """Internal server exception."""

    message: str

    def __post_init__(self):
        super().__init__(self.message)

    def to_dict(self):
        return {"message": self.message}


def calculate_digest(content: bytes) -> str:
    try:
        sha256_hash = hashlib.sha256(content).digest()

        # Encode the hash to base64
        base64_encoded = base64.b64encode(sha256_hash).decode("utf-8")
        return base64_encoded
    except Exception as e:
        logger.error(f"Error calculating checksum: {str(e)}")
        raise


def calculate_file_digest(file_path: str) -> str:
    """calculate_digest of the file at ``file_path``, read 1 MiB at a time."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        for block in iter(lambda: file.read(_STREAM_BLOCK_BYTES), b""):
            sha256.update(block)
    return base64.b64encode(sha256.digest()).decode("utf-8")


def upload_from_presigned_url(
    create_upload_url_response: CreateArtifactUploadUrlResponseTypeDef,
    content: Union[bytes, BinaryIO],
    is_managed_bucket: bool = True,
) -> None:
    presigned_url_string = create_upload_url_response["s3preSignedUrl"]
    headers = {key: value[0] for key, value in create_upload_url_response["requestHeaders"].items()}

    try:
        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=_PRESIGNED_URL_RETRY))
            response = session.put(
                presigned_url_string,
                data=content,
                headers=headers,
                timeout=_PRESIGNED_UPLOAD_TIMEOUT,
            )
    except _TRANSPORT_ERRORS as e:
        raise InternalBaseAgentError("Artifact upload failed: connection error") from e

    raise_for_s3_error_response(response.status_code, response.text, is_managed_bucket)

    logger.info("File uploaded successfully!")


def upload_file_to_presigned_url(
    create_upload_url_response: CreateArtifactUploadUrlResponseTypeDef,
    file_path: str,
    is_managed_bucket: bool = True,
) -> None:
    """upload_from_presigned_url for the file at ``file_path``, streamed from disk.

    A retry rewinds the file and sends it again from its start.
    """
    with open(file_path, "rb") as file:
        # requests sends an empty file object chunked, which S3 rejects; empty bytes go out
        # with Content-Length: 0.
        content = file if os.fstat(file.fileno()).st_size else b""
        upload_from_presigned_url(create_upload_url_response, content, is_managed_bucket)


def download_from_presigned_url(
    create_download_url_response: Union[CreateArtifactDownloadUrlResponseTypeDef, dict],
    destination_file_path: str,
    is_managed_bucket: bool = True,
) -> None:
    """Download to ``destination_file_path``, streamed to disk 1 MiB at a time.

    The file is written in full or not at all: the body goes to a temp file in the same
    directory, which then replaces the destination. A new file gets the mode the umask
    allows; an existing file keeps its mode. A destination that is a symlink is refused, and a
    body over 5 GiB fails the download.
    """
    if os.path.islink(destination_file_path):
        raise ValueError(f"Download destination {destination_file_path} is a symlink")

    try:
        # Support both s3PreSignedUrl (skill download) and s3preSignedUrl (artifact download)
        presigned_url_string = cast(
            str,
            create_download_url_response.get("s3PreSignedUrl")
            or create_download_url_response.get("s3preSignedUrl"),
        )
        if not presigned_url_string:
            raise KeyError("Neither 's3PreSignedUrl' nor 's3preSignedUrl' found in response")

        headers = {
            key: value[0] for key, value in create_download_url_response["requestHeaders"].items()
        }

        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=_PRESIGNED_URL_RETRY))
            response = session.get(
                presigned_url_string,
                headers=headers,
                timeout=_PRESIGNED_DOWNLOAD_TIMEOUT,
                stream=True,
            )
            try:
                if response.status_code >= 400:
                    raise_for_s3_error_response(
                        response.status_code, response.text, is_managed_bucket
                    )
                _write_file_atomically(_body_blocks(response), destination_file_path)
            finally:
                response.close()
    except _TRANSPORT_ERRORS as e:
        raise InternalBaseAgentError("Artifact download failed: connection error") from e

    logger.info(f"File downloaded to {destination_file_path} successfully")


def _body_blocks(response: requests.Response) -> Iterator[bytes]:
    """The body of a streamed ``response``, failing if it is cut short or too long."""
    received = 0
    for block in response.iter_content(_STREAM_BLOCK_BYTES):
        received += len(block)
        if received > _MAX_DOWNLOAD_BYTES:
            raise InternalBaseAgentError(
                f"Artifact download failed: body exceeds {_MAX_DOWNLOAD_BYTES} bytes"
            )
        yield block
    # Bytes of the declared Content-Length that never arrived; None when none was declared.
    if response.raw.length_remaining:
        raise InternalBaseAgentError("Artifact download failed: incomplete body")


def _write_file_atomically(blocks: Iterable[bytes], destination_file_path: str) -> None:
    """Write ``blocks`` to ``destination_file_path`` in full, or on any failure not at all.

    The temp file has a unique name, so concurrent writes to one path each leave a whole file
    and the last replace wins.
    """
    directory = os.path.dirname(os.path.abspath(destination_file_path))
    os.makedirs(directory, exist_ok=True)
    try:
        mode: Optional[int] = stat.S_IMODE(os.stat(destination_file_path).st_mode)
    except FileNotFoundError:
        mode = None
    # Not named after the destination, whose name may leave no room under NAME_MAX.
    temp = os.path.join(directory, f".{uuid.uuid4().hex}.part")
    # 0o666 lets the umask set a new file's mode, as open() does.
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666 if mode is None else 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            for block in blocks:
                file.write(block)
            file.flush()
            os.fsync(file.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, destination_file_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(temp)
        raise


def handle_boto_error(error: ClientError) -> None:
    """Handle boto3 client errors."""
    error_code = error.response["Error"]["Code"]
    error_message = error.response["Error"]["Message"]
    logger.error(f"AgenticApi Error: {error_code} - {error_message}")
    raise error


def raise_for_s3_error_response(status: int, text: str, is_managed_bucket: bool = True) -> None:
    if status < 400:
        return

    try:
        root = DefusedElementTree.fromstring(text)
        if root.tag != "Error":
            raise InternalBaseAgentError(f"Unexpected {status} S3 error: {text}")

        code = root.findtext("Code")
        request_id = root.findtext("RequestId")
        message = root.findtext("Message", "")
        formatted_error = (
            f"{message} (Service: Amazon S3; Status Code: {status}; "
            f"Error Code: {code}; Request ID: {request_id})"
        ).lstrip()

        if code is None or is_managed_bucket:
            raise InternalBaseAgentError(formatted_error)

        if code == "AccessDenied":
            raise UserBaseAgentError(
                formatted_error,
                "Access was denied to an artifact in your configured S3 bucket for AWS Transform "
                "artifact storage. If the bucket configuration was recently changed, please wait "
                "a few minutes before trying again.",
            )
        # These are related to a subscription check / Verify Access To Product (VATP).
        # https://w.amazon.com/bin/view/AWSAuth/APIAuth/ARC/Features/SubscriptionCheck/
        # https://t.corp.amazon.com/V2117359621
        elif code == "AllAccessDisabled" or code == "InvalidPayer":
            raise UserBaseAgentError(
                formatted_error,
                "All access has been disabled to an artifact in your configured S3 bucket for "
                "AWS Transform artifact storage. Contact AWS Support.",
            )
        elif code == "NoSuchBucket":
            bucket_name = root.findtext("BucketName")
            raise UserBaseAgentError(
                f"{formatted_error}, Bucket Name: {bucket_name}",
                "Your configured S3 bucket was not found for AWS Transform artifact storage.",
            )
        elif code == "NoSuchKey":
            raise UserBaseAgentError(
                formatted_error,
                "Cannot find an artifact in your configured S3 bucket for AWS Transform "
                "artifact storage.",
            )
        elif code == "KMS.DisabledException":
            raise UserBaseAgentError(
                formatted_error,
                "Your KMS key is disabled for your configured S3 bucket for AWS Transform "
                "artifact storage.",
            )
        elif code == "KMS.InvalidKeyUsageException":
            raise UserBaseAgentError(
                formatted_error,
                "Your KMS key's KeyUsage or algorithm is invalid for your configured S3 bucket for "
                "AWS Transform artifact storage.",
            )
        elif code == "KMS.KMSInvalidStateException":
            raise UserBaseAgentError(
                formatted_error,
                "Your KMS key is in an invalid state for your configured S3 bucket for AWS "
                "Transform artifact storage.",
            )
        elif code == "KMS.NotFoundException":
            raise UserBaseAgentError(
                formatted_error,
                "Your KMS key was not found for your configured S3 bucket for AWS "
                "Transform artifact storage.",
            )
        elif code == "Slow Down" or code == "503 Slow Down" or code == "SlowDown":
            message = root.findtext("Message", "")
            if "Please reduce your request rate for operations involving AWS KMS." in message:
                raise UserBaseAgentError(
                    formatted_error,
                    "Your KMS request quota was exceed while attempting to access your "
                    "configured S3 bucket for AWS Transform artifact storage.",
                )
            else:
                raise UserBaseAgentError(
                    formatted_error,
                    "Your S3 request quota was exceed while attempting to access your "
                    "configured S3 bucket for AWS Transform artifact storage.",
                )
        else:
            raise InternalBaseAgentError(f"Unexpected {status} S3 error: {text}")
    except ElementTree.ParseError:
        raise InternalBaseAgentError(f"Unexpected {status} S3 error: {text}")
