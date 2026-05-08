import os
import tempfile
from datetime import datetime
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.api_model import CategoryType, Visibility
from agent_builder_sdk.agentic_framework.artifact_store import ArtifactStore
from agent_builder_sdk.errors import UserBaseAgentError
from agent_builder_types import type_defs as abt
from agent_builder_types.client import TransformAgenticServiceClient


@pytest.fixture(autouse=True)
def retrieve_auth_token():
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agentic_api_helper.retrieve_auth_token"
    ):
        yield


@pytest.fixture
def artifact_store(monkeypatch):
    return ArtifactStore(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        client=mock.create_autospec(TransformAgenticServiceClient, spec_set=True, instance=True),
    )


@pytest.fixture
def get_artifact_metadata_response(response_metadata):
    return abt.GetArtifactMetadataResponseTypeDef(
        artifact=abt.ArtifactTypeDef(
            artifactId="123",
            artifactType="",
            artifactCreatedTimestamp=datetime.now(),
            artifactExpiryTimestamp=datetime.now(),
            storedInAtxBucket=True,
        ),
        isS3ObjectPresent=abt.IsS3ObjectPresentTypeDef(publicBucket=True),
        metadata=abt.MetadataContextTypeDef(),
        ResponseMetadata=response_metadata,
    )


class TestListArtifacts:
    """Test cases for list_artifacts method."""

    def test_list_artifacts_with_category_success(self, artifact_store):
        """Test successful listing of artifacts with category."""
        expected_response = {
            "artifacts": [
                {"artifactId": "artifact-1", "createdAt": "2024-01-01T00:00:00Z"},
                {"artifactId": "artifact-2", "createdAt": "2024-01-02T00:00:00Z"},
            ]
        }
        artifact_store.client.list_artifacts.return_value = expected_response

        result = artifact_store.list_artifacts("test-agent-123", CategoryType.STATE)

        assert result == expected_response
        artifact_store.client.list_artifacts.assert_called_once()
        call_args = artifact_store.client.list_artifacts.call_args[1]
        assert call_args["artifactFilter"]["agentFilter"]["agentInstanceId"] == "test-agent-123"
        assert call_args["artifactFilter"]["agentFilter"]["category"] == CategoryType.STATE.value

    def test_list_artifacts_without_category_success(self, artifact_store):
        """Test successful listing of artifacts without category filter."""
        expected_response = {"artifacts": [{"artifactId": "artifact-1"}]}
        artifact_store.client.list_artifacts.return_value = expected_response

        result = artifact_store.list_artifacts("test-agent-123")

        assert result == expected_response
        call_args = artifact_store.client.list_artifacts.call_args[1]
        assert call_args["artifactFilter"]["agentFilter"]["agentInstanceId"] == "test-agent-123"
        assert "category" not in call_args["artifactFilter"]["agentFilter"]

    def test_list_artifacts_client_error(self, artifact_store):
        """Test listing artifacts with client error."""
        artifact_store.client.list_artifacts.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="list_artifacts",
        )

        with pytest.raises(ClientError):
            artifact_store.list_artifacts("test-agent-123", CategoryType.STATE)

    def test_list_artifacts_customer_config_error(self, artifact_store):
        artifact_store.client.list_artifacts.side_effect = ClientError(
            error_response={
                "Error": {"Code": "CustomerConfigurationException", "Message": "Test message"}
            },
            operation_name="list_artifacts",
        )

        with pytest.raises(UserBaseAgentError) as e:
            artifact_store.list_artifacts("test-agent-123", CategoryType.STATE)

        assert e.value.user_facing_message == "Test message"


class TestUploadArtifact:
    """Test cases for upload_artifact method."""

    @mock.patch("agent_builder_sdk.agentic_framework.artifact_store.upload_from_presigned_url")
    def test_upload_artifact_with_artifact_id_success(
        self, mock_upload, artifact_store, get_artifact_metadata_response
    ):
        """Test successful artifact upload with artifact_id."""
        expected_response = {
            "artifactId": "test-artifact-id",
            "s3preSignedUrl": "https://test-upload-url.com",
        }
        artifact_store.client.create_artifact_upload_url.return_value = expected_response
        artifact_store.client.get_artifact_metadata.return_value = get_artifact_metadata_response
        artifact_store.client.complete_artifact_upload.return_value = {}

        result = artifact_store.upload_artifact(
            content=b"test content", digest="test-digest", artifact_id="test-artifact-id"
        )

        assert result == "test-artifact-id"
        mock_upload.assert_called_once_with(expected_response, b"test content", True)
        artifact_store.client.complete_artifact_upload.assert_called_once()

        call_args = artifact_store.client.create_artifact_upload_url.call_args[1]
        assert call_args["contentDigest"]["sha256"] == "test-digest"
        assert call_args["artifactReference"]["artifactId"] == "test-artifact-id"
        assert call_args["visibility"] == Visibility.INTERNAL

    @mock.patch("agent_builder_sdk.agentic_framework.artifact_store.upload_from_presigned_url")
    def test_upload_artifact_with_artifact_type_success(
        self, mock_upload, artifact_store, get_artifact_metadata_response
    ):
        """Test successful artifact upload with category_type and file_type."""
        expected_response = {
            "artifactId": "test-artifact-id",
            "s3preSignedUrl": "https://test-upload-url.com",
        }
        artifact_store.client.create_artifact_upload_url.return_value = expected_response
        artifact_store.client.get_artifact_metadata.return_value = get_artifact_metadata_response
        artifact_store.client.complete_artifact_upload.return_value = {}

        result = artifact_store.upload_artifact(
            content=b"test content", digest="test-digest", category_type="STATE", file_type="ZIP"
        )

        assert result == "test-artifact-id"
        call_args = artifact_store.client.create_artifact_upload_url.call_args[1]
        expected_artifact_type = {
            "categoryType": "STATE",
            "fileType": "ZIP",
        }
        assert call_args["artifactReference"]["artifactType"] == expected_artifact_type

    def test_upload_artifact_validation_neither_provided(self, artifact_store):
        """Test upload artifact validation when neither artifact_id nor category_type/file_type provided."""
        with pytest.raises(
            ValueError, match="Either artifact_id or category_type and file_type must be provided"
        ):
            artifact_store.upload_artifact(content=b"test content", digest="test-digest")

    def test_upload_artifact_validation_both_provided(self, artifact_store):
        """Test upload artifact validation when both artifact_id and category_type provided."""
        with pytest.raises(
            ValueError, match="Cannot provide both artifact_id and category_type or file_type"
        ):
            artifact_store.upload_artifact(
                content=b"test content",
                digest="test-digest",
                artifact_id="test-id",
                category_type="STATE",
            )

    @mock.patch("agent_builder_sdk.agentic_framework.artifact_store.upload_from_presigned_url")
    def test_upload_artifact_with_optional_params(
        self, mock_upload, artifact_store, get_artifact_metadata_response
    ):
        """Test artifact upload with optional parameters."""
        expected_response = {
            "artifactId": "test-artifact-id",
            "s3preSignedUrl": "https://test-upload-url.com",
        }
        artifact_store.client.create_artifact_upload_url.return_value = expected_response
        artifact_store.client.get_artifact_metadata.return_value = get_artifact_metadata_response
        artifact_store.client.complete_artifact_upload.return_value = {}

        result = artifact_store.upload_artifact(
            content=b"test content",
            digest="test-digest",
            category_type="STATE",
            file_type="ZIP",
            plan_step_id="step-123",
            label="test-label",
        )

        assert result == "test-artifact-id"
        call_args = artifact_store.client.create_artifact_upload_url.call_args[1]
        assert call_args["planStepId"] == "step-123"
        assert call_args["label"] == "test-label"

    @mock.patch("agent_builder_sdk.agentic_framework.artifact_store.upload_from_presigned_url")
    def test_upload_artifact_missing_stored_in_atx_bucket(
        self, mock_upload, artifact_store, response_metadata
    ):
        """Test upload succeeds when storedInAtxBucket is absent from metadata."""
        expected_response = {
            "artifactId": "test-artifact-id",
            "s3preSignedUrl": "https://test-upload-url.com",
        }
        metadata_without_field = abt.GetArtifactMetadataResponseTypeDef(
            artifact=abt.ArtifactTypeDef(
                artifactId="123",
                artifactType="",
                artifactCreatedTimestamp=datetime.now(),
                artifactExpiryTimestamp=datetime.now(),
            ),
            isS3ObjectPresent=abt.IsS3ObjectPresentTypeDef(publicBucket=True),
            metadata=abt.MetadataContextTypeDef(),
            ResponseMetadata=response_metadata,
        )
        artifact_store.client.create_artifact_upload_url.return_value = expected_response
        artifact_store.client.get_artifact_metadata.return_value = metadata_without_field
        artifact_store.client.complete_artifact_upload.return_value = {}

        result = artifact_store.upload_artifact(
            content=b"test content", digest="test-digest", artifact_id="test-artifact-id"
        )

        assert result == "test-artifact-id"
        mock_upload.assert_called_once_with(expected_response, b"test content", True)

    def test_upload_artifact_client_error(self, artifact_store):
        """Test upload artifact with client error."""
        artifact_store.client.create_artifact_upload_url.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="create_artifact_upload_url",
        )

        with pytest.raises(ClientError):
            artifact_store.upload_artifact(
                content=b"test content", digest="test-digest", artifact_id="test-id"
            )

    def test_upload_artifact_customer_config_error(self, artifact_store):
        artifact_store.client.create_artifact_upload_url.side_effect = ClientError(
            error_response={
                "Error": {"Code": "CustomerConfigurationException", "Message": "Test message"}
            },
            operation_name="create_artifact_upload_url",
        )

        with pytest.raises(UserBaseAgentError) as e:
            artifact_store.upload_artifact(
                content=b"test content", digest="test-digest", artifact_id="test-id"
            )

        assert e.value.user_facing_message == "Test message"


class TestDownloadArtifact:
    """Test cases for download_artifact method."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.artifact_store.download_from_presigned_url"
    )
    def test_download_artifact_success(self, mock_download, artifact_store):
        """Test successful artifact download."""
        expected_response = {
            "s3preSignedUrl": "https://test-download-url.com",
            "artifact": {"storedInAtxBucket": False},
        }
        artifact_store.client.create_artifact_download_url.return_value = expected_response

        with tempfile.TemporaryDirectory() as temp_dir:
            dest_path = os.path.join(temp_dir, "downloaded_file.zip")

            artifact_store.download_artifact("test-artifact-id", dest_path)

            mock_download.assert_called_once_with(
                expected_response, dest_path, is_managed_bucket=False
            )
            artifact_store.client.create_artifact_download_url.assert_called_once()

            call_args = artifact_store.client.create_artifact_download_url.call_args[1]
            assert call_args["artifactId"] == "test-artifact-id"

    def test_download_artifact_client_error(self, artifact_store):
        """Test download artifact with client error."""
        artifact_store.client.create_artifact_download_url.side_effect = ClientError(
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
            operation_name="create_artifact_download_url",
        )

        with pytest.raises(ClientError):
            artifact_store.download_artifact("test-artifact-id", "/tmp/test.zip")

    def test_download_artifact_customer_config_error(self, artifact_store):
        artifact_store.client.create_artifact_download_url.side_effect = ClientError(
            error_response={
                "Error": {"Code": "CustomerConfigurationException", "Message": "Test message"}
            },
            operation_name="create_artifact_download_url",
        )

        with pytest.raises(UserBaseAgentError) as e:
            artifact_store.download_artifact("test-artifact-id", "/tmp/test.zip")

        assert e.value.user_facing_message == "Test message"
