# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Artifact storage management for agentic framework.
"""

import logging
import os
from typing import cast

from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_sdk.agentic_framework.api_model import CategoryType
from agent_builder_sdk.agentic_framework.common import (
    download_from_presigned_url,
    upload_file_to_presigned_url,
    upload_from_presigned_url,
)
from agent_builder_sdk.errors import UserBaseAgentError
from agent_builder_types import TransformAgenticServiceClient
from agent_builder_types import type_defs as abt
from agent_builder_types.literals import CategoryTypeType, FileTypeType, VisibilityType

logger = logging.getLogger(__name__)


class ArtifactStore(AgenticApiHelper):
    """Manages artifact storage operations."""

    client: TransformAgenticServiceClient

    def list_artifacts(
        self,
        agent_instance_id: str,
        category: CategoryType | None = None,
        next_token: str | None = None,
        max_results: int | None = None,
    ) -> abt.ListArtifactsResponseTypeDef:
        """List artifacts for an agent, newest first, optionally capped at max_results."""
        agent_filter = abt.ArtifactAgentFilterTypeDef(agentInstanceId=agent_instance_id)
        if category is not None:
            agent_filter["category"] = cast(CategoryTypeType, category.value)

        request: dict = {
            "artifactFilter": {"agentFilter": agent_filter},
            "requestContext": self._create_request_context(),
        }
        if next_token is not None:
            request["nextToken"] = next_token
        if max_results is not None:
            request["maxResults"] = max_results

        try:
            return self.client.list_artifacts(**request)
        except Exception as e:
            category_str = category.value if category else None
            message = f"Error listing artifacts for agent {agent_instance_id} with category {category_str}"
            self._raise_for_customer_config_error(e, message)
            logger.exception(message)
            raise

    def upload_artifact(
        self,
        content: bytes,
        digest: str,
        artifact_id: str | None = None,
        category_type: CategoryTypeType | None = None,
        file_type: FileTypeType | None = None,
        plan_step_id: str | None = None,
        label: str | None = None,
        *,
        source_file_path: str | None = None,
        file_name: str | None = None,
        description: str | None = None,
        visibility: VisibilityType = "INTERNAL",
        schema_type: str | None = None,
    ) -> str:
        """Upload artifact with specified category and return its ID.

        ``digest`` is the base64 SHA-256 of the bytes sent: calculate_digest(content), or
        calculate_file_digest(source_file_path).

        ``source_file_path`` uploads that file, streamed from disk, in place of ``content``,
        which must then be empty; a file that cannot be opened raises OSError before any request.
        ``file_name`` is stored as the artifact's file path (at most 838 characters), so a
        download can restore it (see artifact_file_name), and ``description`` (at most 4000
        characters) is stored with it. ``schema_type`` is stored with the type of a new artifact.
        """
        if content and source_file_path is not None:
            raise ValueError("Cannot provide both content and source_file_path")
        if description and not file_name:
            raise ValueError("description is stored with file_name; provide both")
        if source_file_path is not None:
            # A missing or unreadable file must fail before an artifact is created that would
            # never be completed.
            with open(source_file_path, "rb"):
                pass
        artifact_reference: abt.ArtifactReferenceTypeDef
        if artifact_id is not None:
            if category_type is not None or file_type is not None:
                raise ValueError("Cannot provide both artifact_id and category_type or file_type")
            if schema_type is not None:
                raise ValueError("Cannot provide both artifact_id and schema_type")

            artifact_reference = {"artifactId": str(artifact_id)}
        else:
            if category_type is None or file_type is None:
                raise ValueError(
                    "Either artifact_id or category_type and file_type must be provided"
                )

            artifact_reference = {
                "artifactType": {
                    "categoryType": category_type,
                    "fileType": file_type,
                }
            }
            if schema_type:
                artifact_reference["artifactType"]["schemaType"] = schema_type

        request = abt.CreateArtifactUploadUrlRequestRequestTypeDef(
            artifactReference=artifact_reference,
            contentDigest={"sha256": digest},
            visibility=visibility,
            requestContext=self._create_request_context(),
        )

        if plan_step_id:
            request["planStepId"] = plan_step_id

        if label:
            request["label"] = label

        if file_name:
            request["fileMetadata"] = {"path": file_name}
            if description:
                request["fileMetadata"]["description"] = description

        try:
            response = self.client.create_artifact_upload_url(**request)
            artifact_id = response["artifactId"]

            metadata = self.client.get_artifact_metadata(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )

            is_managed_bucket = metadata["artifact"].get("storedInAtxBucket", True)
            if source_file_path is None:
                upload_from_presigned_url(response, content, is_managed_bucket)
            else:
                upload_file_to_presigned_url(response, source_file_path, is_managed_bucket)

            complete_request = abt.CompleteArtifactUploadRequestRequestTypeDef(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )
            self.client.complete_artifact_upload(**complete_request)
        except Exception as e:
            self._raise_for_customer_config_error(e, "Error uploading artifact")
            logger.exception("Error uploading artifact")
            raise

        return artifact_id

    def get_artifact_metadata(self, artifact_id: str) -> abt.GetArtifactMetadataResponseTypeDef:
        """Get the metadata of an artifact by ID."""
        try:
            return self.client.get_artifact_metadata(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )
        except Exception as e:
            message = f"Error getting metadata of artifact {artifact_id}"
            self._raise_for_customer_config_error(e, message)
            logger.exception(message)
            raise

    def download_artifact(
        self,
        artifact_id: str,
        destination_file_path: str,
        *,
        visibility: VisibilityType | None = None,
    ) -> None:
        """Download artifact by ID and put to the destination file path.

        See download_from_presigned_url for how the file is written. ``visibility`` is sent
        with the request only when given.
        """
        try:
            request = abt.CreateArtifactDownloadUrlRequestRequestTypeDef(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )
            if visibility is not None:
                request["visibility"] = visibility
            download_response = self.client.create_artifact_download_url(**request)
            download_from_presigned_url(
                download_response,
                destination_file_path,
                is_managed_bucket=download_response["artifact"].get("storedInAtxBucket", True),
            )
        except Exception as e:
            self._raise_for_customer_config_error(e, f"Error downloading artifact {artifact_id}")
            logger.exception(f"Error downloading artifact {artifact_id}")
            raise

        logger.info(f"Download artifactId[{artifact_id}] to {destination_file_path} successfully")

    def _raise_for_customer_config_error(self, error: Exception, internal_message: str) -> None:
        if isinstance(error, ClientError):
            if error.response["Error"]["Code"] == "CustomerConfigurationException":
                # The error message for this exception is already customer-facing.
                message = error.response["Error"]["Message"]
                raise UserBaseAgentError(internal_message, message) from error


def artifact_file_name(metadata: abt.GetArtifactMetadataResponseTypeDef) -> str:
    """A local file name for the artifact: the last part of its stored file path, else of its
    label, else its ID.

    Only a last part without a drive (Windows ``C:name``) is used, so joining the name to a
    directory stays in that directory.
    """
    artifact = metadata["artifact"]
    file_metadata = artifact.get("fileMetadata")
    candidates = (
        file_metadata["path"] if file_metadata else None,
        artifact.get("artifactLabel"),
        artifact["artifactId"],
    )
    for candidate in candidates:
        name = os.path.basename(candidate or "")
        if name not in ("", ".", "..") and not os.path.splitdrive(name)[0]:
            return name
    raise ValueError(f"Artifact {artifact['artifactId']} has no usable file name")
