# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional
from xml.etree import ElementTree

import requests

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.datamodels import (
    ArtifactReference,
    FileMetadata,
    MetadataContext,
    is_valid_checksum,
)
from agent_builder_agentic_mcp.server._inject_qt_request_context import (
    _get_request_context,
    _inject_qt_request_context,
)
from agent_builder_agentic_mcp.server._server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)

_CUSTOMER_BUCKET_ERROR_MESSAGES: Dict[str, str] = {
    "AccessDenied": (
        "Access was denied to an artifact in the customer-configured S3 bucket for "
        "AWS Transform. If the bucket configuration was recently changed, "
        "please wait a few minutes before trying again."
    ),
    "NoSuchBucket": ("The customer-configured S3 bucket was not found for AWS Transform."),
    "NoSuchKey": (
        "Cannot find an artifact in the customer-configured S3 bucket for AWS Transform."
    ),
    "AllAccessDisabled": (
        "All access has been disabled to the customer-configured S3 bucket for "
        "AWS Transform. Contact AWS Support."
    ),
    "InvalidPayer": (
        "All access has been disabled to the customer-configured S3 bucket for "
        "AWS Transform. Contact AWS Support."
    ),
    "KMS.DisabledException": (
        "The KMS key is disabled for the customer-configured S3 bucket for AWS Transform."
    ),
    "KMS.NotFoundException": (
        "The KMS key was not found for the customer-configured S3 bucket for AWS Transform."
    ),
    "KMS.KMSInvalidStateException": (
        "The KMS key is in an invalid state for the customer-configured S3 bucket for "
        "AWS Transform."
    ),
    "KMS.InvalidKeyUsageException": (
        "The KMS key's KeyUsage or algorithm is invalid for the customer-configured "
        "S3 bucket for AWS Transform."
    ),
}


def _parse_s3_error(response_text: str) -> tuple:
    """Extract the S3 error code and message from an XML error response."""
    try:
        root = ElementTree.fromstring(response_text)
        if root.tag == "Error":
            return root.findtext("Code"), root.findtext("Message", "")
    except ElementTree.ParseError:
        pass
    return None, ""


def _get_customer_facing_message(code: str, message: str) -> Optional[str]:
    """Map an S3 error code to a customer-facing message."""
    result = _CUSTOMER_BUCKET_ERROR_MESSAGES.get(code)
    if result:
        return result
    if code in ("Slow Down", "503 Slow Down", "SlowDown"):
        if "operations involving AWS KMS" in message:
            return (
                "Your KMS request quota was exceeded while attempting to access your "
                "configured S3 bucket for AWS Transform."
            )
        return (
            "Your S3 request quota was exceeded while attempting to access your "
            "configured S3 bucket for AWS Transform."
        )
    return None


def _enrich_s3_error(error_dict: Dict[str, Any], is_managed_bucket: bool = True) -> Dict[str, Any]:
    """Enrich an S3 error dict with customer-facing context for customer-configured buckets.

    When is_managed_bucket is False and the S3 error code matches a known customer
    configuration issue, adds:
        - is_user_error (bool): True if caused by customer bucket misconfiguration.
        - customer_facing_message (str): Message safe to show to the customer.

    Defaults to is_managed_bucket=True so errors are treated as internal unless
    explicitly identified as a customer bucket.
    """
    if is_managed_bucket:
        return error_dict

    error_text = error_dict.get("error", "")
    # The error field is formatted as "Upload failed: <xml>" or "Download failed: <xml>"
    prefix_end = error_text.find(":")
    xml_body = error_text[prefix_end + 1 :].strip() if prefix_end != -1 else error_text

    code, message = _parse_s3_error(xml_body)
    if code:
        customer_message = _get_customer_facing_message(code, message)
        if customer_message:
            error_dict["is_user_error"] = True
            error_dict["customer_facing_message"] = customer_message
    return error_dict


# Artifact Management Tools


# TODO: migrate Dict type to data class
@mcp.tool(
    name="create_artifact_upload_url",
    description="Creates a pre-signed URL for uploading an artifact. The optional visibility (enum: EXTERNAL, INTERNAL), the optional label (string, max length 100), the optional planStepId, the required content_digest must be a valid Sha256Checksum String. The required artifact_reference is a union of either a key of artifactId or a key of artifactType. The value of artifactId should be a UUID. The value of artifactType contains a required field categoryType (enum: AGENT_INPUT, AGENT_OUTPUT, CUSTOMER_INPUT, CUSTOMER_OUTPUT, HITL_FROM_AGENT, HITL_FROM_USER, INTERNAL, STATE, PLAN_STEP_OUTPUT), a required field of fileType (enum: ZIP, JSON, PDF, HTML, TXT, MARKDOWN, CSV, PPTX, XLSX), and an optional field of schemaType (string, max length 100). The optional metadata parameter is a MetadataContext structure with an optional schemaVersion (string) and optional content (Document - any JSON-serializable data). The optional file_metadata parameter contains a required field called path which is the file path passed in that indicates where to store the file, which includes the file name, and a field called description for providing details about the file being uploaded.",
)
async def create_artifact_upload_url(
    content_digest: str,
    artifact_reference: Dict[str, Any],
    label: Optional[str] = None,
    plan_step_id: Optional[str] = None,
    visibility: Optional[str] = "INTERNAL",
    metadata: Optional[Dict[str, Any]] = None,
    file_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Creates a pre-signed URL for uploading an artifact.

    Args:
        content_digest: The sha256 checksum digest string of the content to upload
        artifact_reference: The reference to the artifact
        label: Optional label for the artifact
        plan_step_id: Optional plan step ID
        visibility: Optional visibility setting
        metadata: Optional metadata context with schemaVersion and content
        file_metadata: Optional file metadata with file path and description

    Returns:
        The artifact ID and upload URL
    """
    logger.info("Creating artifact upload URL")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Validate the checksum string
        if not is_valid_checksum(content_digest):
            raise ValueError(
                f"Invalid SHA-256 checksum format: {content_digest}. "
                "Must be a base64 string between 1-64 characters matching the required pattern."
            )

        # Convert string to required dictionary format
        digest_dict = {"sha256": content_digest}

        # Validate and convert artifact_reference
        validated_reference = ArtifactReference.from_dict(artifact_reference).to_dict()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {
            "contentDigest": digest_dict,
            "artifactReference": validated_reference,
        }

        if label:
            kwargs["label"] = label

        if plan_step_id:
            kwargs["planStepId"] = plan_step_id

        if visibility:
            kwargs["visibility"] = visibility

        if metadata:
            metadata_context = MetadataContext.from_dict(metadata)
            processed_dict = metadata_context.to_dict()
            # Convert JSON string content to dict if needed
            if processed_dict.get("content") and isinstance(processed_dict["content"], str):
                processed_dict["content"] = json.loads(processed_dict["content"])
            kwargs["metadata"] = processed_dict

        if file_metadata:
            kwargs["fileMetadata"] = FileMetadata.from_dict(file_metadata).to_dict()

        # Make the API call
        response = client.create_artifact_upload_url(**_inject_qt_request_context(kwargs))

        return {
            "artifactId": response["artifactId"],
            "s3preSignedUrl": response["s3preSignedUrl"],
            "s3UrlExpiryTimestamp": response["s3UrlExpiryTimestamp"],
            "requestHeaders": response["requestHeaders"],
        }
    except Exception as e:
        logger.error(f"Error creating artifact upload URL: {str(e)}")
        raise


@mcp.tool(
    name="upload_artifact",
    description="Upload an artifact with s3preSignedUrl. This tool should only be used after create_artifact_upload_url. Required fields s3_presigned_url, request_headers, and artifact_id should exactly match the complete values of create_artifact_upload_url's response. The file_path should be provided, or in the case where LLM generated an artifact file, the file_path should be known. Only when receiving a success response from upload_artifact, proceed to call complete_artifact_upload.",
)
async def upload_artifact(
    s3_presigned_url: str,
    request_headers: Dict[str, Any],
    artifact_id: str,
    file_path: str,
) -> Dict[str, Any]:
    """
    Upload a file to S3 using a presigned URL with the provided headers.

    Args:
        s3_presigned_url: The presigned S3 URL for upload
        request_headers: Dictionary containing the required headers
        artifact_id: ID of the artifact to be uploaded
        file_path: Path to the file to upload

    Returns:
        Dictionary with upload status and details
    """
    logger.info(f"Uploading artifact with ID: {artifact_id}")

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        headers = {
            key: value[0]
            for key, value in request_headers.items()
            if value and value[0] is not None
        }

        # Read file data
        with open(file_path, "rb") as file:
            file_data = file.read()

        # Make the PUT request
        response = requests.put(s3_presigned_url, data=file_data, headers=headers)

        # Check response
        if response.status_code in [200, 204]:
            return {
                "success": True,
                "status_code": response.status_code,
                "message": "File uploaded successfully",
                "file_size": len(file_data),
                "artifact_id": artifact_id,
                "headers_used": headers,
            }
        else:
            error_result = {
                "success": False,
                "status_code": response.status_code,
                "artifact_id": artifact_id,
                "error": f"Upload failed: {response.text}",
                "headers_used": headers,
            }
            try:
                metadata = await get_artifact_metadata(artifact_id)
                is_managed = metadata.get("artifact", {}).get("storedInAtxBucket", True)
            except Exception:
                logger.warning(f"Failed to fetch artifact metadata for {artifact_id}")
                is_managed = True
            return _enrich_s3_error(error_result, is_managed_bucket=is_managed)

    except Exception as e:
        logger.error(f"Error uploading artifact: {str(e)}")
        raise


@mcp.tool(
    name="complete_artifact_upload",
    description="Completes an artifact upload. This tool should only be used after upload_artifact.",
)
async def complete_artifact_upload(artifact_id: str) -> Dict[str, Any]:
    """
    Completes an artifact upload.

    Args:
        artifact_id: The ID of the artifact

    Returns:
        The artifact information
    """
    logger.info(f"Completing artifact upload for artifact ID: {artifact_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Make the API call
        response = client.complete_artifact_upload(
            requestContext=_get_request_context().to_dict(), artifactId=artifact_id
        )

        return {"artifact": response["artifact"]}
    except Exception as e:
        logger.error(f"Error completing artifact upload: {str(e)}")
        raise


@mcp.tool(
    name="create_artifact_download_url",
    description="Creates a pre-signed URL for downloading an artifact.",
)
async def create_artifact_download_url(
    artifact_id: str, visibility: Optional[str] = "INTERNAL"
) -> Dict[str, Any]:
    """
    Creates a pre-signed URL for downloading an artifact.

    Args:
        artifact_id: The ID of the artifact
        visibility: Optional visibility setting

    Returns:
        The download URL and artifact information
    """
    logger.info(f"Creating artifact download URL for artifact ID: {artifact_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"artifactId": artifact_id}

        if visibility:
            kwargs["visibility"] = visibility

        # Make the API call
        response = client.create_artifact_download_url(**_inject_qt_request_context(kwargs))

        return {
            "s3preSignedUrl": response["s3preSignedUrl"],
            "s3UrlExpiryTimestamp": response["s3UrlExpiryTimestamp"],
            "artifactType": response["artifactType"],
            "artifactLabel": response.get("artifactLabel"),
            "requestHeaders": response["requestHeaders"],
            "artifact": response["artifact"],
        }
    except Exception as e:
        logger.error(f"Error creating artifact download URL: {str(e)}")
        raise


@mcp.tool(
    name="download_artifact",
    description="Download an artifact with s3preSignedUrl. This tool should only be used after create_artifact_download_url. Required fields s3_presigned_url, request_headers, and artifact_id should exactly match the complete values of create_artifact_upload_url's response. The output_dir should be provided",
)
async def download_artifact(
    s3_presigned_url: str,
    request_headers: Dict[str, Any],
    artifact_id: str,
    output_dir: str,
    file_name: Optional[str] = None,
    is_managed_bucket: bool = True,
) -> Dict[str, Any]:
    """
    Download a file to S3 using a presigned URL with the provided headers.
    Args:
        s3_presigned_url: The presigned S3 URL for download
        request_headers: Dictionary containing the required headers
        artifact_id: ID of the artifact to be downloaded
        output_dir: Directory to save the downloaded artifact
        file_name: Optional name of the downloaded artifact
        is_managed_bucket: Whether the artifact is stored in an ATX-managed bucket

    Returns:
        Dictionary with download status and details
    """
    logger.info(f"Downloading artifact with ID: {artifact_id}")

    try:
        # Make sure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        headers = {
            key: value[0]
            for key, value in request_headers.items()
            if value and value[0] is not None
        }

        # Make the GET request
        response = requests.get(s3_presigned_url, stream=True, headers=headers)

        # Check if request was successful
        if response.status_code == 200:
            filename = None

            if file_name:
                filename = file_name
            else:
                filename = "downloaded_file"

            output_path = os.path.join(output_dir, filename)

            # Download the file
            file_size = 0
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        file_size += len(chunk)

            return {
                "success": True,
                "file_path": output_path,
                "file_size": file_size,
                "filename": filename,
                "status_code": response.status_code,
                "message": "File downloaded successfully",
            }
        else:
            return _enrich_s3_error(
                {
                    "success": False,
                    "status_code": response.status_code,
                    "error": f"Download failed: {response.text}",
                },
                is_managed_bucket=is_managed_bucket,
            )

    except Exception as e:
        logger.error(f"Error downloading artifact: {str(e)}")
        raise


@mcp.tool(
    name="list_artifacts",
    description="Lists artifacts for a job. All parameters are optional. The max_results parameter accepts integers between 1 and 100. The artifact_filter parameter is a union type that must contain either an 'agentFilter' key or a 'categoryFilter' key. When using 'agentFilter', it must contain an ArtifactAgentFilter object with a required 'agentInstanceId' field and an optional 'category' field (CategoryType enum). When using 'categoryFilter', it must contain an ArtifactCategoryFilter object with a required 'category' field (CategoryType enum) and an optional 'artifactLabel' field (string with maximum length of 100). The CategoryType enum values are: AGENT_INPUT, AGENT_OUTPUT, CUSTOMER_INPUT, CUSTOMER_OUTPUT, HITL_FROM_AGENT, HITL_FROM_USER, INTERNAL, STATE, PLAN_STEP_OUTPUT. The next_token parameter is used for pagination when results exceed max_results.",
)
async def list_artifacts(
    artifact_filter: Optional[Dict[str, Any]] = None,
    max_results: Optional[int] = None,
    next_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lists artifacts for a job.

    Args:
        artifact_filter: Optional filter for artifacts
        max_results: Optional maximum number of results to return
        next_token: Optional token for pagination

    Returns:
        List of artifacts
    """
    logger.info("Listing artifacts")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {}

        if artifact_filter:
            kwargs["artifactFilter"] = artifact_filter

        if max_results:
            kwargs["maxResults"] = max_results

        if next_token:
            kwargs["nextToken"] = next_token

        # Make the API call
        response = client.list_artifacts(**_inject_qt_request_context(kwargs))

        result = {"artifacts": response["artifacts"]}

        if "nextToken" in response:
            result["nextToken"] = response["nextToken"]

        return result
    except Exception as e:
        logger.error(f"Error listing artifacts: {str(e)}")
        raise


@mcp.tool(
    name="get_artifact_metadata",
    description="Gets metadata for an artifact. This can optionally return additional metadata, which is a MetadataContext structure that consists of an optional schemaVersion (string) and optional content (Document - any JSON-serializable data).",
)
async def get_artifact_metadata(artifact_id: str) -> Dict[str, Any]:
    """
    Gets metadata for an artifact.

    Args:
        artifact_id: The ID of the artifact

    Returns:
        Dict containing artifact metadata including:
        - artifact: The artifact information
        - isS3ObjectPresent: Whether the S3 object is present
        - metadata: (Optional) Additional metadata if available
    """
    logger.info(f"Getting artifact metadata for artifact ID: {artifact_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Make the API call
        response = client.get_artifact_metadata(
            artifactId=artifact_id, requestContext=_get_request_context().to_dict()
        )

        result = {
            "artifact": response["artifact"],
            "isS3ObjectPresent": response["isS3ObjectPresent"],
        }

        # Add metadata if present in response
        if "metadata" in response and response["metadata"] is not None:
            result["metadata"] = response["metadata"]

        return result
    except Exception as e:
        logger.error(f"Error getting artifact metadata: {str(e)}")
        raise


@mcp.tool(name="copy_artifact", description="Copies an artifact.")
async def copy_artifact(artifact_id: str) -> Dict[str, Any]:
    """
    Copies an artifact.

    Args:
        artifact_id: The ID of the artifact to copy

    Returns:
        The copy status
    """
    logger.info(f"Copying artifact with ID: {artifact_id}")

    try:
        # Get the client using the cached function
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {"artifactId": artifact_id}

        # Generate a UUID for idempotency
        kwargs["idempotencyToken"] = str(uuid.uuid4())

        # Make the API call
        response = client.copy_artifact(**_inject_qt_request_context(kwargs))

        return {"copyStatus": response["copyStatus"]}
    except Exception as e:
        logger.error(f"Error copying artifact: {str(e)}")
        raise
