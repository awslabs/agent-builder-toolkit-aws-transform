"""
Artifact storage management for agentic framework.
"""

import logging
from typing import cast

from botocore.exceptions import ClientError
from agent_builder_types import TransformAgenticServiceClient
from agent_builder_types import type_defs as abt
from agent_builder_types.literals import CategoryTypeType, FileTypeType

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_sdk.agentic_framework.api_model import CategoryType
from agent_builder_sdk.agentic_framework.common import (
    download_from_presigned_url,
    upload_from_presigned_url,
)
from agent_builder_sdk.errors import UserBaseAgentError

logger = logging.getLogger(__name__)


class ArtifactStore(AgenticApiHelper):
    """Manages artifact storage operations."""

    client: TransformAgenticServiceClient

    def list_artifacts(
        self, agent_instance_id: str, category: CategoryType | None = None
    ) -> abt.ListArtifactsResponseTypeDef:
        """List artifacts by agent instance ID and category type."""
        agent_filter = abt.ArtifactAgentFilterTypeDef(agentInstanceId=agent_instance_id)
        if category is not None:
            agent_filter["category"] = cast(CategoryTypeType, category.value)

        try:
            return self.client.list_artifacts(
                artifactFilter={"agentFilter": agent_filter},
                requestContext=self._create_request_context(),
            )
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
    ) -> str:
        """Upload artifact with specified category and return its ID."""
        artifact_reference: abt.ArtifactReferenceTypeDef
        if artifact_id is not None:
            if category_type is not None or file_type is not None:
                raise ValueError("Cannot provide both artifact_id and category_type or file_type")

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

        request = abt.CreateArtifactUploadUrlRequestRequestTypeDef(
            artifactReference=artifact_reference,
            contentDigest={"sha256": digest},
            visibility="INTERNAL",
            requestContext=self._create_request_context(),
        )

        if plan_step_id:
            request["planStepId"] = plan_step_id

        if label:
            request["label"] = label

        try:
            response = self.client.create_artifact_upload_url(**request)
            artifact_id = response["artifactId"]

            metadata = self.client.get_artifact_metadata(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )

            upload_from_presigned_url(
                response, content, metadata["artifact"].get("storedInAtxBucket", True)
            )

            complete_request = abt.CompleteArtifactUploadRequestRequestTypeDef(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )
            self.client.complete_artifact_upload(**complete_request)
        except Exception as e:
            self._raise_for_customer_config_error(e, "Error uploading artifact")
            logger.exception("Error uploading artifact")
            raise

        return artifact_id

    def download_artifact(self, artifact_id: str, destination_file_path: str) -> None:
        """Download artifact by ID and put to the destination file path."""
        try:
            download_response = self.client.create_artifact_download_url(
                artifactId=artifact_id, requestContext=self._create_request_context()
            )
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
