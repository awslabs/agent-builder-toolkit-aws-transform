# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint repository for agent state/memory/conversation persistence.
"""

import json
import logging
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from agent_builder_sdk.agent_state.agent_state import IAgentState
from agent_builder_sdk.agentic_framework.api_model import CategoryType
from agent_builder_sdk.agentic_framework.artifact_store import ArtifactStore
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.agentic_framework.common import calculate_digest
from agent_builder_sdk.env_var import get_agent_context_from_env
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_types.type_defs import ArtifactTypeDef

logger = logging.getLogger(__name__)


class CheckpointRepository:
    """Manages agent checkpointing operations."""

    def __init__(
        self,
        workspace_id: str,
        job_id: str,
        agent_instance_id: str,
        checkpoint_location: Optional[str] = None,
        client=None,
        auto_check_state_object: Optional[bool] = False,
    ):
        """Initialize CheckpointRepository."""
        self.workspace_id = workspace_id
        self.job_id = job_id
        self.agent_instance_id = agent_instance_id
        self.checkpoint_location = checkpoint_location or self._get_default_location()
        self.auto_check_state_object = auto_check_state_object
        # Only set True after restore_if_available() observes remote state (restored
        # or confirmed empty). Stays False if the list/download fails — e.g. when
        # the auth-credential update races startup restore — so CheckpointManager
        # can refuse to overwrite remote state with a possibly-empty local copy.
        self._restore_verified = False
        self.artifact_store = ArtifactStore(
            workspace_id=workspace_id,
            job_id=job_id,
            agent_instance_id=agent_instance_id,
            client=client,
        )

    @property
    def is_restore_verified(self) -> bool:
        """Whether a restore has been verified (successful restore or confirmed empty)."""
        return self._restore_verified

    def _get_default_location(self) -> str:
        """Get default checkpoint location."""
        return "/tmp/agent_state"

    def _copy_state_to_location(
        self, state: IAgentState, location: Optional[str] = None
    ) -> Optional[str]:
        """
        Serializes IAgentState object to bytes and writes to specified location.

        Args:
            state: The agent state object to serialize
            location: File path to write to. If None, generates default path.

        Returns:
            The file path if successful, None otherwise.
        """
        try:
            source_path = location or self.checkpoint_location
            logger.info(f"Copying files to location : {source_path}")

            # Convert to JSON bytes
            state_dict = state.to_dict()
            json_bytes = json.dumps(state_dict, indent=2).encode("utf-8")

            with open(source_path, "wb") as f:
                f.write(json_bytes)

            return source_path

        except Exception as e:
            print(f"Error copying state to location: {e}")
            return None

    def create_checkpoint(
        self, location: Optional[str] = None, agent_state: Optional[IAgentState] = None
    ) -> Optional[str]:
        """Create new checkpoint - only when none exists."""
        try:
            if self.auto_check_state_object:
                assert agent_state is not None
                self._copy_state_to_location(agent_state, location)
            source_path = location or self.checkpoint_location
            logger.info(f"Creating checkpoint from {source_path}")

            # Create ZIP from source path
            zip_content = self._create_zip_from_path(source_path)
            if zip_content is None:
                logger.info("No files to checkpoint, skipping artifact creation")
                return None

            # Calculate digest
            digest = calculate_digest(zip_content)

            # Upload checkpoint with artifact_type
            artifact_id = self.artifact_store.upload_artifact(
                content=zip_content, digest=digest, category_type="STATE", file_type="ZIP"
            )
            if artifact_id:
                logger.info(f"Checkpoint created with artifactId: {artifact_id}")
                return artifact_id
            else:
                logger.warning("Checkpoint creation failed")
                return None
        except Exception:
            logger.exception(f"Failed to create checkpoint from {source_path}")
            raise

    def update_checkpoint(
        self, existing_checkpoint: ArtifactTypeDef | None = None, location: Optional[str] = None
    ) -> bool:
        """Update existing checkpoint - override current one."""
        try:
            source_path = location or self.checkpoint_location
            logger.info(f"Updating checkpoint from {source_path}")

            # Get existing checkpoint if not provided
            if existing_checkpoint is None:
                checkpoints = self.list_checkpoint()
                if not checkpoints:
                    logger.warning("No existing checkpoint to update")
                    return False
                existing_checkpoint = checkpoints[0]

            existing_artifact_id = existing_checkpoint["artifactId"]

            # Create ZIP from source path
            zip_content = self._create_zip_from_path(source_path)
            if zip_content is None:
                logger.info("No files to checkpoint, skipping update")
                return False

            # Calculate digest
            digest = calculate_digest(zip_content)

            # Update checkpoint with existing artifact_id
            response = self.artifact_store.upload_artifact(
                content=zip_content, digest=digest, artifact_id=existing_artifact_id
            )

            success = response is not None
            logger.info(f"Checkpoint update {'succeeded' if success else 'failed'}")
            return success

        except Exception:
            logger.exception(f"Failed to update checkpoint from {source_path}")
            raise

    def retrieve_checkpoint(self, destination_path: str) -> None:
        """Download and extract checkpoint."""
        try:
            logger.info(f"Retrieving checkpoint to {destination_path}")

            # Get existing checkpoint
            checkpoints = self.list_checkpoint()
            if not checkpoints:
                logger.info("No checkpoint available to retrieve")
                return

            artifact_id = checkpoints[0]["artifactId"]

            # Download to temporary file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as temp_file:
                temp_zip_path = temp_file.name
                self.artifact_store.download_artifact(artifact_id, temp_zip_path)
                self._extract_zip_to_path(temp_zip_path, destination_path)

            logger.info(f"Checkpoint retrieved to {destination_path}")

        except Exception:
            logger.exception(f"Failed to retrieve checkpoint to {destination_path}")
            raise

    def list_checkpoint(self) -> list[ArtifactTypeDef]:
        """List available checkpoints for this agent (should be 0 or 1)."""
        try:
            response = self.artifact_store.list_artifacts(
                self.agent_instance_id, CategoryType.STATE
            )
            checkpoint_artifacts = response.get("artifacts", [])
            logger.info(f"Found {len(checkpoint_artifacts)} checkpoint artifacts")
            return checkpoint_artifacts
        except Exception:
            logger.exception(f"Failed to list checkpoints for agent {self.agent_instance_id}")
            raise

    def _create_zip_from_path(self, source_path: str) -> bytes | None:
        """Create ZIP content from source path. Returns None if no files to checkpoint."""
        source = Path(source_path)

        # Check if path exists and has content
        if not source.exists():
            logger.warning(f"Source path does not exist, skipping checkpoint: {source_path}")
            return None

        if source.is_file():
            # Single file exists
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.write(source, source.name)
            zip_content = zip_buffer.getvalue()
            size_kb = len(zip_content) / 1024
            logger.info(f"Created checkpoint ZIP from file: {size_kb:.2f} KB")
            return zip_content

        elif source.is_dir():
            # Check if directory has any files
            has_files = any(file_path.is_file() for file_path in source.rglob("*"))
            if not has_files:
                logger.warning(
                    f"Directory exists but contains no files, skipping checkpoint: {source_path}"
                )
                return None

            # Directory has files, create zip
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in source.rglob("*"):
                    arcname = file_path.relative_to(source)
                    if file_path.is_file():
                        zip_file.write(file_path, arcname)
                    elif file_path.is_dir():
                        # Only add empty directories (non-empty ones are implicitly created by their files)
                        if not any(file_path.iterdir()):
                            zip_file.writestr(str(arcname) + "/", "")
            zip_content = zip_buffer.getvalue()
            size_kb = len(zip_content) / 1024
            logger.info(f"Created checkpoint ZIP from directory: {size_kb:.2f} KB")
            return zip_content

        else:
            logger.warning(
                f"Source path is neither file nor directory, skipping checkpoint: {source_path}"
            )
            return None

    def _extract_zip_to_path(self, zip_file_path: str, destination_path: str) -> None:
        """Extract ZIP file to destination path."""
        destination = Path(destination_path)
        destination.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_file_path, "r") as zip_file:
            zip_file.extractall(destination)

    def restore_if_available(self) -> bool:
        """Restore checkpoint if available, return True if restored."""
        try:
            checkpoints = self.list_checkpoint()
            if checkpoints:
                self.retrieve_checkpoint(self.checkpoint_location)
                self._restore_verified = True
                logger.info(f"Checkpoint restored to {self.checkpoint_location}")
                return True
            else:
                self._restore_verified = True
                logger.info("No checkpoint available to restore")
                return False
        except Exception:
            logger.warning("Failed to restore checkpoint:", exc_info=True)
            return False


def create_checkpoint_repository(
    checkpoint_location: Optional[str], context: Optional[AgentRuntimeContext] = None
) -> CheckpointRepository:
    """Create CheckpointRepository from environment variables."""
    if context is None:
        # TODO: remove this tweak when we remove get_agent_context_from_env()
        # Convert AgenticApiRequestContext to AgentRuntimeContext
        env_context = get_agent_context_from_env()
        context = AgentRuntimeContext(
            workspace_id=env_context.workspace_id,
            job_id=env_context.job_id,
            agent_instance_id=env_context.agent_instance_id,
            initial_auth_token=env_context.authorization_token,
        )

    client = get_agentic_api_client()

    return CheckpointRepository(
        workspace_id=context.workspace_id,
        job_id=context.job_id,
        agent_instance_id=context.agent_instance_id,
        checkpoint_location=checkpoint_location,
        client=client,
    )
