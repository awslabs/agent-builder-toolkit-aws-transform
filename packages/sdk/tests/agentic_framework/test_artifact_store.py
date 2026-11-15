# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
from datetime import datetime
from typing import Any, Optional
from unittest import mock

import botocore.session
import pytest
from botocore.exceptions import ClientError
from botocore.model import ServiceModel
from botocore.validate import validate_parameters

from agent_builder_sdk.agentic_framework.api_model import CategoryType, Visibility
from agent_builder_sdk.agentic_framework.artifact_store import ArtifactStore, artifact_file_name
from agent_builder_sdk.agentic_framework.client_factory import PACKAGED_MODELS_DIR
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

    def test_list_artifacts_forwards_next_token(self, artifact_store):
        """next_token is forwarded to the client; omitted when None."""
        artifact_store.client.list_artifacts.return_value = {"artifacts": []}

        artifact_store.list_artifacts("test-agent-123", CategoryType.STATE, next_token="tok")

        assert artifact_store.client.list_artifacts.call_args[1]["nextToken"] == "tok"

        artifact_store.list_artifacts("test-agent-123", CategoryType.STATE)

        assert "nextToken" not in artifact_store.client.list_artifacts.call_args[1]

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


_MODULE = "agent_builder_sdk.agentic_framework.artifact_store"
_UPLOAD_PATCH = f"{_MODULE}.upload_from_presigned_url"
_FILE_UPLOAD_PATCH = f"{_MODULE}.upload_file_to_presigned_url"
_DOWNLOAD_PATCH = f"{_MODULE}.download_from_presigned_url"


def _assert_valid_request(operation: str, request: dict[str, Any]) -> None:
    """Raises if the bundled service model does not accept ``request`` for ``operation``."""
    loader = botocore.session.get_session().get_component("data_loader")
    loader.search_paths.append(PACKAGED_MODELS_DIR)
    model = ServiceModel(loader.load_service_model("transformagenticservice", "service-2"))
    context = {**request["requestContext"], "authorizationToken": "token"}
    validate_parameters(
        {**request, "requestContext": context}, model.operation_model(operation).input_shape
    )


@pytest.fixture
def upload_url_response() -> dict[str, Any]:
    return {"artifactId": "a1", "s3preSignedUrl": "https://u", "requestHeaders": {}}


@pytest.fixture
def uploading_store(
    artifact_store: ArtifactStore,
    upload_url_response: dict[str, Any],
    get_artifact_metadata_response: abt.GetArtifactMetadataResponseTypeDef,
) -> ArtifactStore:
    artifact_store.client.create_artifact_upload_url.return_value = upload_url_response
    artifact_store.client.get_artifact_metadata.return_value = get_artifact_metadata_response
    return artifact_store


class TestUploadReleaseCallForms:
    """The call forms of release 1.1.0 send the same requests as before."""

    @pytest.mark.parametrize(
        ("args", "kwargs", "reference"),
        [
            (
                (b"x", "d", None, "STATE", "ZIP", "step-1", "l"),
                {},
                {"artifactType": {"categoryType": "STATE", "fileType": "ZIP"}},
            ),
            (
                (),
                {"content": b"x", "digest": "d", "artifact_id": "a1", "label": "l"},
                {"artifactId": "a1"},
            ),
        ],
        ids=["positional", "keyword"],
    )
    @mock.patch(_UPLOAD_PATCH)
    def test_request_is_unchanged(
        self,
        mock_upload: mock.Mock,
        uploading_store: ArtifactStore,
        upload_url_response: dict[str, Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        reference: dict[str, Any],
    ) -> None:
        uploading_store.upload_artifact(*args, **kwargs)

        request = uploading_store.client.create_artifact_upload_url.call_args.kwargs
        expected = {
            "artifactReference": reference,
            "contentDigest": {"sha256": "d"},
            "visibility": "INTERNAL",
            "requestContext": uploading_store._create_request_context(),
            "label": "l",
        }
        if args:
            expected["planStepId"] = "step-1"
        assert request == expected
        mock_upload.assert_called_once_with(upload_url_response, b"x", True)

    def test_new_keywords_are_keyword_only(self, artifact_store: ArtifactStore) -> None:
        with pytest.raises(TypeError):
            artifact_store.upload_artifact(  # type: ignore[misc]
                b"x", "d", None, "STATE", "ZIP", None, None, "/tmp/f"
            )


class TestUploadKeywords:
    @mock.patch(_UPLOAD_PATCH)
    def test_keywords_reach_a_request_the_model_accepts(
        self, mock_upload: mock.Mock, uploading_store: ArtifactStore
    ) -> None:
        uploading_store.upload_artifact(
            b"x",
            "d",
            category_type="CUSTOMER_OUTPUT",
            file_type="CSV",
            file_name="reports/out.csv",
            description="Totals",
            visibility="EXTERNAL",
            schema_type="report-v1",
        )

        request = uploading_store.client.create_artifact_upload_url.call_args.kwargs
        assert request["visibility"] == "EXTERNAL"
        assert request["fileMetadata"] == {"path": "reports/out.csv", "description": "Totals"}
        assert request["artifactReference"]["artifactType"]["schemaType"] == "report-v1"
        _assert_valid_request("CreateArtifactUploadUrl", request)

    @mock.patch(_UPLOAD_PATCH)
    def test_file_name_without_description(
        self, mock_upload: mock.Mock, uploading_store: ArtifactStore
    ) -> None:
        uploading_store.upload_artifact(b"x", "d", artifact_id="a1", file_name="out.csv")

        request = uploading_store.client.create_artifact_upload_url.call_args.kwargs
        assert request["fileMetadata"] == {"path": "out.csv"}
        _assert_valid_request("CreateArtifactUploadUrl", request)

    @mock.patch(_UPLOAD_PATCH)
    @mock.patch(_FILE_UPLOAD_PATCH)
    def test_source_file_path_is_uploaded_from_disk(
        self,
        mock_file_upload: mock.Mock,
        mock_upload: mock.Mock,
        uploading_store: ArtifactStore,
        upload_url_response: dict[str, Any],
    ) -> None:
        uploading_store.upload_artifact(b"", "d", artifact_id="a1", source_file_path="/data/f.csv")

        mock_file_upload.assert_called_once_with(upload_url_response, "/data/f.csv", True)
        mock_upload.assert_not_called()
        uploading_store.client.complete_artifact_upload.assert_called_once()

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"content": b"x", "source_file_path": "/f"}, "content and source_file_path"),
            ({"description": "no name"}, "description is stored with file_name"),
            ({"artifact_id": "a1", "schema_type": "s"}, "artifact_id and schema_type"),
        ],
    )
    def test_invalid_combination_sends_no_request(
        self, artifact_store: ArtifactStore, kwargs: dict[str, Any], message: str
    ) -> None:
        call: dict[str, Any] = {"content": b"", "digest": "d", **kwargs}
        if "artifact_id" not in call:
            call.update(category_type="STATE", file_type="ZIP")

        with pytest.raises(ValueError, match=message):
            artifact_store.upload_artifact(**call)

        artifact_store.client.create_artifact_upload_url.assert_not_called()


class TestDownloadVisibility:
    @pytest.mark.parametrize("visibility", [None, "INTERNAL", "EXTERNAL"])
    @mock.patch(_DOWNLOAD_PATCH)
    def test_visibility_is_sent_only_when_given(
        self, mock_download: mock.Mock, artifact_store: ArtifactStore, visibility: Optional[str]
    ) -> None:
        response = {"s3preSignedUrl": "https://u", "artifact": {"storedInAtxBucket": True}}
        artifact_store.client.create_artifact_download_url.return_value = response

        artifact_store.download_artifact("a1", "/tmp/a1.zip", visibility=visibility)

        expected = {"artifactId": "a1", "requestContext": artifact_store._create_request_context()}
        if visibility is not None:
            expected["visibility"] = visibility
        artifact_store.client.create_artifact_download_url.assert_called_once_with(**expected)
        _assert_valid_request("CreateArtifactDownloadUrl", expected)
        mock_download.assert_called_once_with(response, "/tmp/a1.zip", is_managed_bucket=True)


class TestGetArtifactMetadata:
    def test_returns_the_service_response(
        self,
        artifact_store: ArtifactStore,
        get_artifact_metadata_response: abt.GetArtifactMetadataResponseTypeDef,
    ) -> None:
        artifact_store.client.get_artifact_metadata.return_value = get_artifact_metadata_response

        assert artifact_store.get_artifact_metadata("a1") is get_artifact_metadata_response

        request = artifact_store.client.get_artifact_metadata.call_args.kwargs
        assert request == {
            "artifactId": "a1",
            "requestContext": artifact_store._create_request_context(),
        }
        _assert_valid_request("GetArtifactMetadata", request)

    def test_raises_the_service_error(self, artifact_store: ArtifactStore) -> None:
        error = ClientError(
            error_response={"Error": {"Code": "ResourceNotFoundException", "Message": "nope"}},
            operation_name="get_artifact_metadata",
        )
        artifact_store.client.get_artifact_metadata.side_effect = error

        with pytest.raises(ClientError) as e:
            artifact_store.get_artifact_metadata("a1")

        assert e.value is error

    def test_customer_config_error(self, artifact_store: ArtifactStore) -> None:
        artifact_store.client.get_artifact_metadata.side_effect = ClientError(
            error_response={
                "Error": {"Code": "CustomerConfigurationException", "Message": "Fix storage"}
            },
            operation_name="get_artifact_metadata",
        )

        with pytest.raises(UserBaseAgentError) as e:
            artifact_store.get_artifact_metadata("a1")

        assert e.value.user_facing_message == "Fix storage"


@pytest.mark.parametrize(
    ("artifact", "name"),
    [
        ({"fileMetadata": {"path": "x/report.csv"}, "artifactLabel": "l"}, "report.csv"),
        ({"fileMetadata": {"path": "../../etc/passwd"}}, "passwd"),
        ({"artifactLabel": "state bundle"}, "state bundle"),
        ({"fileMetadata": {"path": "x/.."}, "artifactLabel": ".."}, "a-1"),
        ({}, "a-1"),
    ],
)
def test_artifact_file_name(artifact: dict[str, Any], name: str) -> None:
    metadata: Any = {"artifact": {"artifactId": "a-1", **artifact}, "isS3ObjectPresent": {}}

    assert artifact_file_name(metadata) == name


def test_artifact_file_name_refuses_an_unusable_id() -> None:
    metadata: Any = {"artifact": {"artifactId": ".."}, "isS3ObjectPresent": {}}

    with pytest.raises(ValueError, match="no usable file name"):
        artifact_file_name(metadata)
