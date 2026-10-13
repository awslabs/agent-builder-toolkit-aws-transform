# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Common utilities for agentic framework.
"""

import base64
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Union, cast
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
# would otherwise block the caller forever. urllib3 applies the connect value to every
# socket write while it sends the request, not only to connecting, which is why the
# upload body is streamed (see upload_from_presigned_url). The upload read timeout is the
# wait for S3 to acknowledge the PUT after the body has been sent, which for a large
# artifact runs longer than any single read while streaming a download, so it is not held
# to the same bound.
_PRESIGNED_UPLOAD_TIMEOUT = (5, 300)
_PRESIGNED_DOWNLOAD_TIMEOUT = (5, 60)

# ConnectTimeout subclasses ConnectionError, but ReadTimeout does not, so catching only
# ConnectionError would let the timeouts above escape as an unhandled ReadTimeout.
_TRANSPORT_ERRORS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)


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


def upload_from_presigned_url(
    create_upload_url_response: CreateArtifactUploadUrlResponseTypeDef,
    content: bytes,
    is_managed_bucket: bool = True,
) -> None:
    presigned_url_string = create_upload_url_response["s3preSignedUrl"]
    headers = {key: value[0] for key, value in create_upload_url_response["requestHeaders"].items()}

    try:
        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=_PRESIGNED_URL_RETRY))
            response = session.put(
                presigned_url_string,
                # Streamed, so the connect timeout bounds each small write rather than one
                # write of the whole body; urllib3 rewinds the stream for a retry. An empty
                # body stays bytes: requests sends an empty stream chunked, which S3 rejects,
                # but empty bytes with Content-Length: 0.
                data=io.BytesIO(content) if content else content,
                headers=headers,
                timeout=_PRESIGNED_UPLOAD_TIMEOUT,
            )
    except _TRANSPORT_ERRORS as e:
        raise InternalBaseAgentError("Artifact upload failed: connection error") from e

    raise_for_s3_error_response(response.status_code, response.text, is_managed_bucket)

    logger.info("File uploaded successfully!")


def download_from_presigned_url(
    create_download_url_response: Union[CreateArtifactDownloadUrlResponseTypeDef, dict],
    destination_file_path: str,
    is_managed_bucket: bool = True,
) -> None:

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
                presigned_url_string, headers=headers, timeout=_PRESIGNED_DOWNLOAD_TIMEOUT
            )
    except _TRANSPORT_ERRORS as e:
        raise InternalBaseAgentError("Artifact download failed: connection error") from e

    raise_for_s3_error_response(
        response.status_code,
        response.text,
        is_managed_bucket,
    )

    path = Path(destination_file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)

    logger.info(f"File downloaded to {destination_file_path} successfully")


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
