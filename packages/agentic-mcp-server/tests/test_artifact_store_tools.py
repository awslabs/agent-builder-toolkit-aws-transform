# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the artifact store tools functionality.
"""

import os
from unittest import mock

import pytest
from agent_builder_agentic_mcp.datamodels import AgenticRequestContext

# Import the module
from agent_builder_agentic_mcp.server._artifact_store_tools import (
    _enrich_s3_error,
    complete_artifact_upload,
    copy_artifact,
    create_artifact_download_url,
    create_artifact_upload_url,
    download_artifact,
    get_artifact_metadata,
    list_artifacts,
    upload_artifact,
)


@pytest.fixture
def mock_request_context():
    """Mock the request context injection."""

    def mock_inject(kwargs):
        # Preserve the original kwargs and add requestContext
        result = kwargs.copy() if kwargs else {}
        result["requestContext"] = AgenticRequestContext(
            job_id="test-job-id",
            workspace_id="test-workspace-id",
            agent_instance_id="test-agent-id",
            authorization_token="test-token",
        )
        return result

    patcher = mock.patch(
        "agent_builder_agentic_mcp.server._artifact_store_tools._inject_qt_request_context",
        mock_inject,
    )
    patcher.start()
    yield mock_inject
    patcher.stop()


@pytest.fixture
def mock_get_request_context():
    """Mock the get_request_context function."""
    context = AgenticRequestContext(
        job_id="test-job-id",
        workspace_id="test-workspace-id",
        agent_instance_id="test-agent-id",
        authorization_token="test-token",
    )

    patcher = mock.patch(
        "agent_builder_agentic_mcp.server._artifact_store_tools._get_request_context",
        return_value=context,
    )
    patcher.start()
    yield context
    patcher.stop()


@pytest.fixture
def mock_atx_client():
    """Mock the ATX client."""
    magic_mock = mock.MagicMock()
    with mock.patch(
        "agent_builder_agentic_mcp.server._artifact_store_tools.atx_agenticapi_client"
    ) as mock_atx_client:
        mock_atx_client.return_value = magic_mock
        yield mock_atx_client.return_value


@pytest.fixture
def sample_artifact():
    """Return a sample artifact response."""
    return {
        "artifactId": "test-artifact-id",
        "jobId": "test-job-id",
        "workspaceId": "test-workspace-id",
        "artifactType": {
            "categoryType": "CUSTOMER_OUTPUT",
            "fileType": "TXT",
            "schemaType": "NONE",
        },
        "artifactLabel": "Test Artifact",
        "createdAt": 1748275200000,
    }


@pytest.mark.anyio
async def test_create_artifact_upload_url(mock_atx_client, mock_request_context):
    """Test creating an artifact upload URL."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        label="Test Label",
        visibility="PUBLIC",
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert call_args["label"] == "Test Label"
    assert call_args["visibility"] == "PUBLIC"
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"
    assert result["s3preSignedUrl"] == "https://test-bucket.s3.amazonaws.com/test-key"
    assert result["s3UrlExpiryTimestamp"] == 1748278800000
    assert result["requestHeaders"] == {"Content-Type": "text/plain"}


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_metadata(mock_atx_client, mock_request_context):
    """Test creating an artifact upload URL with metadata."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {"schemaVersion": "1.0", "content": {"key": "value", "description": "test metadata"}}

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with metadata
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert "metadata" in call_args
    assert call_args["metadata"]["schemaVersion"] == "1.0"
    assert call_args["metadata"]["content"]["key"] == "value"
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_json_string_metadata(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with JSON string content in metadata."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {
        "schemaVersion": "1.0",
        "content": '{"key": "value", "description": "test metadata"}',  # JSON string
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with JSON string metadata
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
    )

    # Verify the mock was called with parsed JSON content
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert "metadata" in call_args
    assert call_args["metadata"]["schemaVersion"] == "1.0"
    # Content should be parsed from JSON string to dict
    assert isinstance(call_args["metadata"]["content"], dict)
    assert call_args["metadata"]["content"]["key"] == "value"

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_metadata_schema_version_only(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with metadata containing only schema version."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {
        "schemaVersion": "2.0"
        # No content field
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with schema version only
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert "metadata" in call_args
    assert call_args["metadata"]["schemaVersion"] == "2.0"
    assert "content" not in call_args["metadata"]

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_metadata_content_only(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with metadata containing only content."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {
        "content": {"data": "test", "type": "example"}
        # No schemaVersion field
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with content only
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert "metadata" in call_args
    assert "schemaVersion" not in call_args["metadata"]
    assert call_args["metadata"]["content"]["data"] == "test"

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_file_metadata_only_path(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with file metadata."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {"schemaVersion": "1.0", "content": {"key": "value", "description": "test metadata"}}
    file_metadata = {"path": "test.txt"}

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with metadata
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
        file_metadata=file_metadata,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert "metadata" in call_args
    assert call_args["metadata"]["schemaVersion"] == "1.0"
    assert call_args["metadata"]["content"]["key"] == "value"
    assert "requestContext" in call_args
    assert "fileMetadata" in call_args
    assert call_args["fileMetadata"]["path"] == "test.txt"

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_file_metadata_description(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with file metadata."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {"schemaVersion": "1.0", "content": {"key": "value", "description": "test metadata"}}
    file_metadata = {"path": "/path/to/file/test.txt", "description": "test file description"}

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with metadata
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
        file_metadata=file_metadata,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert "metadata" in call_args
    assert call_args["metadata"]["schemaVersion"] == "1.0"
    assert call_args["metadata"]["content"]["key"] == "value"
    assert "requestContext" in call_args
    assert "fileMetadata" in call_args
    assert call_args["fileMetadata"]["path"] == "/path/to/file/test.txt"
    assert call_args["fileMetadata"]["description"] == "test file description"

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_plan_step_id(mock_atx_client, mock_request_context):
    """Test creating an artifact upload URL with plan step ID."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with plan_step_id
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        plan_step_id="test-plan-step-id",
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert call_args["planStepId"] == "test-plan-step-id"
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_invalid_json_metadata(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with invalid JSON string in metadata content."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {
        "schemaVersion": "1.0",
        "content": '{"key": "value", "invalid": json}',  # Invalid JSON string
    }

    # Call the function and expect an exception due to invalid JSON
    with pytest.raises(Exception):
        await create_artifact_upload_url(
            content_digest,
            artifact_reference,
            metadata=metadata,
        )

    # Verify the mock was not called due to JSON parsing error
    mock_atx_client.create_artifact_upload_url.assert_not_called()


@pytest.mark.anyio
async def test_complete_artifact_upload(mock_atx_client, mock_get_request_context, sample_artifact):
    """Test completing an artifact upload."""
    # Mock response
    mock_atx_client.complete_artifact_upload.return_value = {"artifact": sample_artifact}

    # Call the function
    result = await complete_artifact_upload("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.complete_artifact_upload.assert_called_once()
    call_args = mock_atx_client.complete_artifact_upload.call_args[1]
    print(call_args)
    assert call_args["artifactId"] == "test-artifact-id"
    assert call_args["requestContext"] == mock_get_request_context.to_dict()

    # Verify the result
    assert result["artifact"] == sample_artifact


@pytest.mark.anyio
async def test_create_artifact_download_url(mock_atx_client, mock_request_context, sample_artifact):
    """Test creating an artifact download URL."""
    # Mock response
    mock_atx_client.create_artifact_download_url.return_value = {
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key-download",
        "s3UrlExpiryTimestamp": 1748278800000,
        "artifactType": {
            "categoryType": "CUSTOMER_OUTPUT",
            "fileType": "TXT",
            "schemaType": "NONE",
        },
        "artifactLabel": "Test Artifact",
        "requestHeaders": {"Content-Type": "text/plain"},
        "artifact": sample_artifact,
    }

    # Call the function
    result = await create_artifact_download_url("test-artifact-id", visibility="PUBLIC")

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_download_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_download_url.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert call_args["visibility"] == "PUBLIC"
    assert "requestContext" in call_args

    # Verify the result
    assert result["s3preSignedUrl"] == "https://test-bucket.s3.amazonaws.com/test-key-download"
    assert result["s3UrlExpiryTimestamp"] == 1748278800000
    assert result["artifactType"]["categoryType"] == "CUSTOMER_OUTPUT"
    assert result["artifactType"]["fileType"] == "TXT"
    assert result["artifactType"]["schemaType"] == "NONE"
    assert result["artifactLabel"] == "Test Artifact"
    assert result["requestHeaders"] == {"Content-Type": "text/plain"}
    assert result["artifact"]["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_list_artifacts(mock_atx_client, mock_request_context, sample_artifact):
    """Test listing artifacts."""
    # Sample artifacts data
    artifacts_data = [sample_artifact]

    # Mock response
    mock_atx_client.list_artifacts.return_value = {
        "artifacts": artifacts_data,
        "nextToken": "next-page-token",
    }

    # Call the function with optional parameters
    result = await list_artifacts(
        {"artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT"}},
        10,
        "page-token",
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.list_artifacts.assert_called_once()
    call_args = mock_atx_client.list_artifacts.call_args[1]
    assert call_args["artifactFilter"] == {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT"}
    }
    assert call_args["maxResults"] == 10
    assert call_args["nextToken"] == "page-token"
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifacts"] == artifacts_data
    assert result["nextToken"] == "next-page-token"


@pytest.mark.anyio
async def test_get_artifact_metadata(mock_atx_client, mock_get_request_context, sample_artifact):
    """Test getting artifact metadata."""
    # Mock response
    mock_atx_client.get_artifact_metadata.return_value = {
        "artifact": sample_artifact,
        "isS3ObjectPresent": True,
    }

    # Call the function
    result = await get_artifact_metadata("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.get_artifact_metadata.assert_called_once()
    call_args = mock_atx_client.get_artifact_metadata.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert call_args["requestContext"] == mock_get_request_context.to_dict()

    # Verify the result
    assert result["artifact"] == sample_artifact
    assert result["isS3ObjectPresent"] is True


@pytest.mark.anyio
async def test_get_artifact_metadata_with_metadata(
    mock_atx_client, mock_get_request_context, sample_artifact
):
    """Test getting artifact metadata with metadata present."""
    # Mock response with metadata
    mock_atx_client.get_artifact_metadata.return_value = {
        "artifact": sample_artifact,
        "isS3ObjectPresent": True,
        "metadata": {
            "schemaVersion": "1.0",
            "content": {"key": "value", "nested": {"data": "test"}},
        },
    }

    # Call the function
    result = await get_artifact_metadata("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.get_artifact_metadata.assert_called_once()
    call_args = mock_atx_client.get_artifact_metadata.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert call_args["requestContext"] == mock_get_request_context.to_dict()

    # Verify the result includes metadata
    assert result["artifact"] == sample_artifact
    assert result["isS3ObjectPresent"] is True
    assert "metadata" in result
    assert result["metadata"]["schemaVersion"] == "1.0"
    assert result["metadata"]["content"]["key"] == "value"
    assert result["metadata"]["content"]["nested"]["data"] == "test"
    assert isinstance(result["metadata"]["content"], dict)
    assert len(result["metadata"]["content"]) == 2


@pytest.mark.anyio
async def test_copy_artifact(mock_atx_client, mock_request_context):
    """Test copying an artifact."""
    # Mock response
    mock_atx_client.copy_artifact.return_value = {"copyStatus": "COMPLETED"}

    # Call the function
    result = await copy_artifact("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.copy_artifact.assert_called_once()
    call_args = mock_atx_client.copy_artifact.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert "idempotencyToken" in call_args

    # Verify the result
    assert result["copyStatus"] == "COMPLETED"


@pytest.mark.anyio
async def test_create_artifact_upload_url_minimal(mock_atx_client, mock_request_context):
    """Test creating an artifact upload URL with minimal parameters."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function with minimal parameters
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
    )

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert call_args["visibility"] == "INTERNAL"
    assert "label" not in call_args
    assert "planStepId" not in call_args
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_download_url_minimal(
    mock_atx_client, mock_request_context, sample_artifact
):
    """Test creating an artifact download URL with minimal parameters."""
    # Mock response
    mock_atx_client.create_artifact_download_url.return_value = {
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key-download",
        "s3UrlExpiryTimestamp": 1748278800000,
        "artifactType": {
            "categoryType": "CUSTOMER_OUTPUT",
            "fileType": "TXT",
            "schemaType": "NONE",
        },
        "artifactLabel": "Test Artifact",
        "requestHeaders": {"Content-Type": "text/plain"},
        "artifact": sample_artifact,
    }

    # Call the function with minimal parameters
    result = await create_artifact_download_url("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.create_artifact_download_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_download_url.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert call_args["visibility"] == "INTERNAL"
    assert "requestContext" in call_args

    # Verify the result
    assert result["s3preSignedUrl"] == "https://test-bucket.s3.amazonaws.com/test-key-download"
    assert result["artifact"]["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_list_artifacts_minimal(mock_atx_client, mock_request_context, sample_artifact):
    """Test listing artifacts with minimal parameters."""
    # Sample artifacts data
    artifacts_data = [sample_artifact]

    # Mock response
    mock_atx_client.list_artifacts.return_value = {
        "artifacts": artifacts_data,
    }

    # Call the function with no parameters
    result = await list_artifacts()

    # Verify the mock was called with the right parameters
    mock_atx_client.list_artifacts.assert_called_once()
    call_args = mock_atx_client.list_artifacts.call_args[1]
    assert len(call_args) == 1  # Only requestContext should be present
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifacts"] == artifacts_data
    assert "nextToken" not in result


@pytest.mark.anyio
async def test_list_artifacts_with_next_token(
    mock_atx_client, mock_request_context, sample_artifact
):
    """Test listing artifacts with next token in response."""
    # Sample artifacts data
    artifacts_data = [sample_artifact]

    # Mock response with nextToken
    mock_atx_client.list_artifacts.return_value = {
        "artifacts": artifacts_data,
        "nextToken": "next-page-token",
    }

    # Call the function
    result = await list_artifacts()

    # Verify the mock was called with the right parameters
    mock_atx_client.list_artifacts.assert_called_once()

    # Verify the result includes nextToken
    assert result["artifacts"] == artifacts_data
    assert result["nextToken"] == "next-page-token"


@pytest.mark.anyio
async def test_copy_artifact_minimal(mock_atx_client, mock_request_context):
    """Test copying an artifact with minimal parameters."""
    # Mock response
    mock_atx_client.copy_artifact.return_value = {"copyStatus": "COMPLETED"}

    # Call the function with minimal parameters
    result = await copy_artifact("test-artifact-id")

    # Verify the mock was called with the right parameters
    mock_atx_client.copy_artifact.assert_called_once()
    call_args = mock_atx_client.copy_artifact.call_args[1]
    assert call_args["artifactId"] == "test-artifact-id"
    assert "idempotencyToken" in call_args

    # Verify the result
    assert result["copyStatus"] == "COMPLETED"


@pytest.mark.anyio
async def test_create_artifact_upload_url_error(mock_atx_client, mock_request_context):
    """Test error handling in create_artifact_upload_url."""
    # Sample data
    content_digest = "AAAA"  # Valid base64 string
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Set up the mock to raise an exception
    mock_atx_client.create_artifact_upload_url.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await create_artifact_upload_url(
            content_digest,
            artifact_reference,
        )

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.create_artifact_upload_url.assert_called_once()


@pytest.mark.anyio
async def test_complete_artifact_upload_error(mock_atx_client, mock_get_request_context):
    """Test error handling in complete_artifact_upload."""
    # Set up the mock to raise an exception
    mock_atx_client.complete_artifact_upload.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await complete_artifact_upload("test-artifact-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.complete_artifact_upload.assert_called_once()


@pytest.mark.anyio
async def test_create_artifact_download_url_error(mock_atx_client, mock_request_context):
    """Test error handling in create_artifact_download_url."""
    # Set up the mock to raise an exception
    mock_atx_client.create_artifact_download_url.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await create_artifact_download_url("test-artifact-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.create_artifact_download_url.assert_called_once()


@pytest.mark.anyio
async def test_list_artifacts_error(mock_atx_client, mock_request_context):
    """Test error handling in list_artifacts."""
    # Set up the mock to raise an exception
    mock_atx_client.list_artifacts.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await list_artifacts()

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.list_artifacts.assert_called_once()


@pytest.mark.anyio
async def test_get_artifact_metadata_error(mock_atx_client, mock_get_request_context):
    """Test error handling in get_artifact_metadata."""
    # Set up the mock to raise an exception
    mock_atx_client.get_artifact_metadata.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await get_artifact_metadata("test-artifact-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.get_artifact_metadata.assert_called_once()


@pytest.mark.anyio
async def test_copy_artifact_error(mock_atx_client, mock_request_context):
    """Test error handling in copy_artifact."""
    # Set up the mock to raise an exception
    mock_atx_client.copy_artifact.side_effect = Exception("Test error")

    # Call the function and expect an exception
    with pytest.raises(Exception) as exc_info:
        await copy_artifact("test-artifact-id")

    # Verify the exception
    assert "Test error" in str(exc_info.value)
    mock_atx_client.copy_artifact.assert_called_once()


@pytest.mark.anyio
async def test_create_artifact_upload_url_validates_content_digest(
    mock_atx_client, mock_request_context
):
    """Test that create_artifact_upload_url validates the content digest."""
    # Sample data with valid base64 sha256
    content_digest = "AAAA"
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call the function
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
    )

    # Verify the mock was called with validated content_digest
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"


@pytest.mark.anyio
async def test_create_artifact_upload_url_invalid_content_digest(
    mock_atx_client, mock_request_context
):
    """Test that create_artifact_upload_url raises an error for invalid content digest."""
    # Sample data with invalid sha256 (contains invalid character)
    content_digest = "A!BC"
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Call the function and expect an exception
    with pytest.raises(ValueError) as exc_info:
        await create_artifact_upload_url(
            content_digest,
            artifact_reference,
        )

    # Verify the exception
    assert "base64 string" in str(exc_info.value)
    mock_atx_client.create_artifact_upload_url.assert_not_called()


@pytest.mark.anyio
async def test_create_artifact_upload_url_missing_sha256(mock_atx_client, mock_request_context):
    """Test that create_artifact_upload_url raises an error when sha256 is missing."""
    # Sample data with missing sha256
    content_digest = ""
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }

    # Call the function and expect an exception
    with pytest.raises(ValueError) as exc_info:
        await create_artifact_upload_url(
            content_digest,
            artifact_reference,
        )

    # Verify the exception
    assert "must be a base64 string" in str(exc_info.value).lower()
    mock_atx_client.create_artifact_upload_url.assert_not_called()


@pytest.mark.anyio
async def test_create_artifact_upload_url_with_empty_metadata(
    mock_atx_client, mock_request_context
):
    """Test creating an artifact upload URL with empty metadata."""
    content_digest = "AAAA"
    artifact_reference = {
        "artifactType": {"categoryType": "CUSTOMER_OUTPUT", "fileType": "TXT", "schemaType": "NONE"}
    }
    metadata = {}

    # Mock response
    mock_atx_client.create_artifact_upload_url.return_value = {
        "artifactId": "test-artifact-id",
        "s3preSignedUrl": "https://test-bucket.s3.amazonaws.com/test-key",
        "s3UrlExpiryTimestamp": 1748278800000,
        "requestHeaders": {"Content-Type": "text/plain"},
    }

    # Call function and verify behavior with empty metadata
    result = await create_artifact_upload_url(
        content_digest,
        artifact_reference,
        metadata=metadata,
    )

    # Verify the mock was called with empty metadata
    mock_atx_client.create_artifact_upload_url.assert_called_once()
    call_args = mock_atx_client.create_artifact_upload_url.call_args[1]
    assert call_args["contentDigest"] == {"sha256": content_digest}
    assert call_args["artifactReference"] == artifact_reference
    assert "metadata" not in call_args  # Empty metadata should not be passed
    assert "requestContext" in call_args

    # Verify the result
    assert result["artifactId"] == "test-artifact-id"
    assert result["s3preSignedUrl"] == "https://test-bucket.s3.amazonaws.com/test-key"


@pytest.mark.anyio
async def test_upload_artifact_success(monkeypatch, tmp_path):
    """Test successful artifact upload."""
    # Create a temporary file for testing
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")

    # Mock the requests.put method
    mock_response = mock.MagicMock()
    mock_response.status_code = 200

    with mock.patch("requests.put", return_value=mock_response):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {
            "Content-Type": ["text/plain"],
            "x-amz-expected-bucket-owner": ["123456789012"],
            "x-amz-server-side-encryption": ["AES256"],
            "x-amz-checksum-sha256": ["checksum"],
            "X-Amz-Credential": ["credential"],
            "x-amz-server-side-encryption-aws-kms-key-id": ["key-id"],
            "x-amz-server-side-encryption-context": ["context"],
        }
        artifact_id = "test-artifact-id"

        # Call the function
        result = await upload_artifact(
            s3_presigned_url, request_headers, artifact_id, str(test_file)
        )

        # Verify the result
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["message"] == "File uploaded successfully"
        assert result["artifact_id"] == artifact_id
        assert "file_size" in result
        assert "headers_used" in result


@pytest.mark.anyio
async def test_upload_artifact_forwards_all_headers(tmp_path):
    """Test that upload_artifact forwards all request headers including new ones."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200

    with mock.patch("requests.put", return_value=mock_response) as mock_put:
        request_headers = {
            "Content-Type": ["text/plain"],
            "X-Amz-Credential": ["credential"],
            "x-amz-new-future-header": ["future-value"],
            "x-amz-server-side-encryption-aws-kms-key-id": [None],
        }
        await upload_artifact(
            "https://test-bucket.s3.amazonaws.com/test-key",
            request_headers,
            "test-artifact-id",
            str(test_file),
        )
        actual_headers = mock_put.call_args[1]["headers"]
        assert actual_headers == {
            "Content-Type": "text/plain",
            "X-Amz-Credential": "credential",
            "x-amz-new-future-header": "future-value",
        }


@pytest.mark.anyio
async def test_upload_artifact_skips_empty_list_headers(tmp_path):
    """Test that upload_artifact skips headers with empty list values."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200

    with mock.patch("requests.put", return_value=mock_response) as mock_put:
        request_headers = {
            "Content-Type": ["text/plain"],
            "x-amz-empty-header": [],
        }
        await upload_artifact(
            "https://test-bucket.s3.amazonaws.com/test-key",
            request_headers,
            "test-artifact-id",
            str(test_file),
        )
        actual_headers = mock_put.call_args[1]["headers"]
        assert actual_headers == {"Content-Type": "text/plain"}


@pytest.mark.anyio
async def test_upload_artifact_file_not_found():
    """Test upload_artifact with a non-existent file."""
    # Test data
    s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
    request_headers = {"Content-Type": ["text/plain"]}
    artifact_id = "test-artifact-id"
    file_path = "/non/existent/file.txt"

    # Call the function
    result = await upload_artifact(s3_presigned_url, request_headers, artifact_id, file_path)

    # Verify the result
    assert result["success"] is False
    assert "File not found" in result["error"]


@pytest.mark.anyio
async def test_upload_artifact_request_failure(monkeypatch, tmp_path):
    """Test upload_artifact when the request fails."""
    # Create a temporary file for testing
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")

    # Mock the requests.put method to return an error
    mock_response = mock.MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Access Denied"

    with mock.patch("requests.put", return_value=mock_response):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"Content-Type": ["text/plain"]}
        artifact_id = "test-artifact-id"

        # Call the function
        result = await upload_artifact(
            s3_presigned_url, request_headers, artifact_id, str(test_file)
        )

        # Verify the result
        assert result["success"] is False
        assert result["status_code"] == 403
        assert "Access Denied" in result["error"]
        assert result["artifact_id"] == artifact_id


@pytest.mark.anyio
async def test_upload_artifact_exception(monkeypatch, tmp_path):
    """Test upload_artifact when an exception occurs."""
    # Create a temporary file for testing
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")

    # Mock the requests.put method to raise an exception
    with mock.patch("requests.put", side_effect=Exception("Test error")):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"Content-Type": ["text/plain"]}
        artifact_id = "test-artifact-id"

        # Call the function and expect an exception
        with pytest.raises(Exception) as exc_info:
            await upload_artifact(s3_presigned_url, request_headers, artifact_id, str(test_file))

        # Verify the exception
        assert "Test error" in str(exc_info.value)


@pytest.mark.anyio
async def test_download_artifact_success(monkeypatch, tmp_path):
    """Test successful artifact download."""
    # Create a mock response with content
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"Test", b" ", b"content"]

    with mock.patch("requests.get", return_value=mock_response) as mock_get:
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"X-Amz-Credential": ["credential"]}
        artifact_id = "test-artifact-id"
        output_dir = str(tmp_path)
        file_name = "downloaded_test_file.txt"

        # Call the function
        result = await download_artifact(
            s3_presigned_url, request_headers, artifact_id, output_dir, file_name
        )

        # Verify the result
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["message"] == "File downloaded successfully"
        assert result["filename"] == file_name
        assert os.path.exists(result["file_path"])

        # Verify the file content
        with open(result["file_path"], "rb") as f:
            content = f.read()
            assert content == b"Test content"

        # Verify the mock was called with the right parameters
        mock_get.assert_called_once_with(
            s3_presigned_url, stream=True, headers={"X-Amz-Credential": "credential"}
        )


@pytest.mark.anyio
async def test_download_artifact_forwards_all_headers(tmp_path):
    """Test that download_artifact forwards all request headers including new ones."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"Test content"]

    with mock.patch("requests.get", return_value=mock_response) as mock_get:
        request_headers = {
            "X-Amz-Credential": ["credential"],
            "Content-Type": ["application/octet-stream"],
            "x-amz-new-future-header": ["future-value"],
            "x-amz-nullable-header": [None],
        }
        await download_artifact(
            "https://test-bucket.s3.amazonaws.com/test-key",
            request_headers,
            "test-artifact-id",
            str(tmp_path),
            "test.zip",
        )
        mock_get.assert_called_once_with(
            "https://test-bucket.s3.amazonaws.com/test-key",
            stream=True,
            headers={
                "X-Amz-Credential": "credential",
                "Content-Type": "application/octet-stream",
                "x-amz-new-future-header": "future-value",
            },
        )


@pytest.mark.anyio
async def test_download_artifact_skips_empty_list_headers(tmp_path):
    """Test that download_artifact skips headers with empty list values."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"Test content"]

    with mock.patch("requests.get", return_value=mock_response) as mock_get:
        request_headers = {
            "X-Amz-Credential": ["credential"],
            "x-amz-empty-header": [],
        }
        await download_artifact(
            "https://test-bucket.s3.amazonaws.com/test-key",
            request_headers,
            "test-artifact-id",
            str(tmp_path),
            "test.zip",
        )
        mock_get.assert_called_once_with(
            "https://test-bucket.s3.amazonaws.com/test-key",
            stream=True,
            headers={"X-Amz-Credential": "credential"},
        )


@pytest.mark.anyio
async def test_download_artifact_default_filename(monkeypatch, tmp_path):
    """Test download_artifact with default filename."""
    # Create a mock response with content
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"Test content"]

    with mock.patch("requests.get", return_value=mock_response):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"X-Amz-Credential": ["credential"]}
        artifact_id = "test-artifact-id"
        output_dir = str(tmp_path)

        # Call the function without specifying a filename
        result = await download_artifact(s3_presigned_url, request_headers, artifact_id, output_dir)

        # Verify the result
        assert result["success"] is True
        assert result["filename"] == "downloaded_file"
        assert os.path.exists(result["file_path"])


@pytest.mark.anyio
async def test_download_artifact_request_failure(monkeypatch):
    """Test download_artifact when the request fails."""
    # Mock the requests.get method to return an error
    mock_response = mock.MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with mock.patch("requests.get", return_value=mock_response):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"X-Amz-Credential": ["credential"]}
        artifact_id = "test-artifact-id"
        output_dir = "/tmp"

        # Call the function
        result = await download_artifact(s3_presigned_url, request_headers, artifact_id, output_dir)

        # Verify the result
        assert result["success"] is False
        assert result["status_code"] == 404
        assert "Not Found" in result["error"]


@pytest.mark.anyio
async def test_download_artifact_exception(monkeypatch):
    """Test download_artifact when an exception occurs."""
    # Mock the requests.get method to raise an exception
    with mock.patch("requests.get", side_effect=Exception("Test error")):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"X-Amz-Credential": ["credential"]}
        artifact_id = "test-artifact-id"
        output_dir = "/tmp"

        # Call the function and expect an exception
        with pytest.raises(Exception) as exc_info:
            await download_artifact(s3_presigned_url, request_headers, artifact_id, output_dir)

        # Verify the exception
        assert "Test error" in str(exc_info.value)


@pytest.mark.anyio
async def test_download_artifact_creates_directory(monkeypatch, tmp_path):
    """Test that download_artifact creates the output directory if it doesn't exist."""
    # Create a mock response with content
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b"Test content"]

    with mock.patch("requests.get", return_value=mock_response):
        # Test data
        s3_presigned_url = "https://test-bucket.s3.amazonaws.com/test-key"
        request_headers = {"X-Amz-Credential": ["credential"]}
        artifact_id = "test-artifact-id"
        output_dir = str(tmp_path / "new_dir")  # Directory doesn't exist yet

        # Call the function
        result = await download_artifact(s3_presigned_url, request_headers, artifact_id, output_dir)

        # Verify the result
        assert result["success"] is True
        assert os.path.exists(output_dir)  # Directory should be created
        assert os.path.exists(result["file_path"])


# Tests for S3 error enrichment


class TestEnrichS3Error:
    """Test cases for _enrich_s3_error."""

    def test_customer_bucket_access_denied(self):
        error_dict = {
            "success": False,
            "status_code": 403,
            "error": "Upload failed: <Error><Code>AccessDenied</Code>"
            "<Message>Access Denied</Message></Error>",
        }
        result = _enrich_s3_error(error_dict, is_managed_bucket=False)
        assert result["is_user_error"] is True
        assert "customer-configured S3 bucket" in result["customer_facing_message"]

    def test_managed_bucket_skips_enrichment(self):
        error_dict = {
            "success": False,
            "status_code": 403,
            "error": "Upload failed: <Error><Code>AccessDenied</Code></Error>",
        }
        result = _enrich_s3_error(error_dict, is_managed_bucket=True)
        assert "is_user_error" not in result
        assert "customer_facing_message" not in result

    def test_unknown_s3_error_code_not_enriched(self):
        error_dict = {
            "success": False,
            "status_code": 500,
            "error": "Upload failed: <Error><Code>InternalError</Code></Error>",
        }
        result = _enrich_s3_error(error_dict, is_managed_bucket=False)
        assert "is_user_error" not in result

    def test_non_xml_error_not_enriched(self):
        error_dict = {
            "success": False,
            "status_code": 500,
            "error": "Upload failed: Internal Server Error",
        }
        result = _enrich_s3_error(error_dict, is_managed_bucket=False)
        assert "is_user_error" not in result


@pytest.mark.anyio
async def test_upload_artifact_customer_bucket_error(monkeypatch, tmp_path):
    """Test upload_artifact enriches error for customer-configured bucket."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")

    mock_response = mock.MagicMock()
    mock_response.status_code = 403
    mock_response.text = "<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"

    async def mock_get_metadata(artifact_id):
        return {"artifact": {"storedInAtxBucket": False}}

    with mock.patch("requests.put", return_value=mock_response), mock.patch(
        "agent_builder_agentic_mcp.server._artifact_store_tools.get_artifact_metadata",
        side_effect=mock_get_metadata,
    ):
        result = await upload_artifact(
            "https://bucket.s3.amazonaws.com/key",
            {"Content-Type": ["text/plain"]},
            "test-artifact-id",
            str(test_file),
        )

        assert result["success"] is False
        assert result["is_user_error"] is True
        assert "customer-configured S3 bucket" in result["customer_facing_message"]


@pytest.mark.anyio
async def test_upload_artifact_managed_bucket_no_enrichment(monkeypatch, tmp_path):
    """Test upload_artifact does not enrich error for ATX-managed bucket."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("Test content")

    mock_response = mock.MagicMock()
    mock_response.status_code = 403
    mock_response.text = "<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>"

    async def mock_get_metadata(artifact_id):
        return {"artifact": {"storedInAtxBucket": True}}

    with mock.patch("requests.put", return_value=mock_response), mock.patch(
        "agent_builder_agentic_mcp.server._artifact_store_tools.get_artifact_metadata",
        side_effect=mock_get_metadata,
    ):
        result = await upload_artifact(
            "https://bucket.s3.amazonaws.com/key",
            {"Content-Type": ["text/plain"]},
            "test-artifact-id",
            str(test_file),
        )

        assert result["success"] is False
        assert "is_user_error" not in result


@pytest.mark.anyio
async def test_download_artifact_customer_bucket_error(tmp_path):
    """Test download_artifact enriches error for customer-configured bucket."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 404
    mock_response.text = "<Error><Code>NoSuchKey</Code><Message>Not Found</Message></Error>"

    with mock.patch("requests.get", return_value=mock_response):
        result = await download_artifact(
            "https://bucket.s3.amazonaws.com/key",
            {},
            "test-artifact-id",
            str(tmp_path),
            is_managed_bucket=False,
        )

        assert result["success"] is False
        assert result["is_user_error"] is True
        assert "Cannot find an artifact" in result["customer_facing_message"]
