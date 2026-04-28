"""
Common utilities for agentic framework.
"""

import base64
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Union, cast
from xml.etree import ElementTree

import requests
from botocore.exceptions import ClientError
from defusedxml import ElementTree as DefusedElementTree
from mypy_boto3_elasticgumbyagenticservice.type_defs import (
    CreateArtifactDownloadUrlResponseTypeDef,
    CreateArtifactUploadUrlResponseTypeDef,
)
from requests.adapters import HTTPAdapter

from agent_builder_sdk.errors import InternalBaseAgentError, UserBaseAgentError

logger = logging.getLogger(__name__)


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
            session.mount("https://", HTTPAdapter(max_retries=3))
            response = session.put(presigned_url_string, data=content, headers=headers)
    except requests.exceptions.ConnectionError as e:
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
            session.mount("https://", HTTPAdapter(max_retries=3))
            response = session.get(presigned_url_string, headers=headers)
    except requests.exceptions.ConnectionError as e:
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
