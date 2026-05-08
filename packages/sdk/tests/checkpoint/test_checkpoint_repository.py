# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for checkpoint manager.
"""

import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.agent_state.agent_state import IAgentState
from agent_builder_sdk.checkpoint.checkpoint_repository import (
    CheckpointRepository,
    create_checkpoint_repository,
)
from agent_builder_sdk.server.server_models import AgentRuntimeContext


@pytest.fixture
def mock_artifact_store():
    """Mock ArtifactStore for testing."""
    return Mock()


@pytest.fixture
def checkpoint_repository(mock_artifact_store):
    """Create CheckpointRepository with mocked dependencies."""
    with patch(
        "agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore",
        return_value=mock_artifact_store,
    ):
        return CheckpointRepository("ws1", "job1", "agent1")


class DummyState(IAgentState):
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IAgentState":
        return DummyState()

    def to_dict(self) -> Dict[str, Any]:
        return {}

    dummy_field: str


@pytest.fixture
def agent_state():
    return DummyState()


@pytest.fixture
def checkpoint_repository_with_object_state_data_type(mock_artifact_store):
    """Create CheckpointRepository with mocked dependencies."""
    with patch(
        "agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore",
        return_value=mock_artifact_store,
    ):
        return CheckpointRepository("ws1", "job1", "agent1", auto_check_state_object=True)


@pytest.fixture
def temp_checkpoint_dir():
    """Create temporary directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("test content")
        yield temp_dir


class TestCheckpointRepository:
    """Test CheckpointRepository functionality."""

    def test_init(self, checkpoint_repository):
        """Test initialization."""
        assert checkpoint_repository.workspace_id == "ws1"
        assert checkpoint_repository.job_id == "job1"
        assert checkpoint_repository.agent_instance_id == "agent1"
        assert checkpoint_repository.checkpoint_location == "/tmp/agent_state"


class TestCreateCheckpointRepository:
    """Test create_checkpoint_repository function."""

    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore")
    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.get_agentic_api_client")
    def test_create_with_context(self, mock_get_client, mock_artifact_store_class):
        """Test create_checkpoint_repository with provided context."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="test-token",
        )

        result = create_checkpoint_repository("/test/path", context)

        assert isinstance(result, CheckpointRepository)
        assert result.workspace_id == "test-workspace"
        assert result.job_id == "test-job"
        assert result.agent_instance_id == "test-agent"
        assert result.checkpoint_location == "/test/path"

    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore")
    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.get_agentic_api_client")
    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.get_agent_context_from_env")
    def test_create_without_context(
        self, mock_get_env_context, mock_get_client, mock_artifact_store_class
    ):
        """Test create_checkpoint_repository without context (uses env)."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock environment context
        mock_env_context = Mock()
        mock_env_context.workspace_id = "env-workspace"
        mock_env_context.job_id = "env-job"
        mock_env_context.agent_instance_id = "env-agent"
        mock_env_context.authorization_token = "env-token"
        mock_get_env_context.return_value = mock_env_context

        result = create_checkpoint_repository("/test/path", None)

        assert isinstance(result, CheckpointRepository)
        assert result.workspace_id == "env-workspace"
        assert result.job_id == "env-job"
        assert result.agent_instance_id == "env-agent"
        assert result.checkpoint_location == "/test/path"

        # Verify env context was called
        mock_get_env_context.assert_called_once()

    def test_create_checkpoint_success_state_data_type_object(
        self,
        checkpoint_repository_with_object_state_data_type,
        mock_artifact_store,
        temp_checkpoint_dir,
        agent_state,
    ):
        """Test successful checkpoint creation."""
        mock_artifact_store.upload_artifact.return_value = "artifact123"

        artifact_id = checkpoint_repository_with_object_state_data_type.create_checkpoint(
            temp_checkpoint_dir, agent_state=DummyState()
        )

        assert artifact_id == "artifact123"
        mock_artifact_store.upload_artifact.assert_called_once()

    def test_create_checkpoint_success(
        self, checkpoint_repository, mock_artifact_store, temp_checkpoint_dir
    ):
        """Test successful checkpoint creation."""
        mock_artifact_store.upload_artifact.return_value = "artifact123"

        artifact_id = checkpoint_repository.create_checkpoint(temp_checkpoint_dir)

        assert artifact_id == "artifact123"
        mock_artifact_store.upload_artifact.assert_called_once()

    def test_update_checkpoint_success_with_existing_checkpoint(
        self, checkpoint_repository, mock_artifact_store, temp_checkpoint_dir
    ):
        """Test successful checkpoint update with existing checkpoint provided."""
        existing_checkpoint = {"artifactId": "existing123"}
        mock_artifact_store.upload_artifact.return_value = "existing123"

        success = checkpoint_repository.update_checkpoint(
            existing_checkpoint=existing_checkpoint, location=temp_checkpoint_dir
        )

        assert success is True
        mock_artifact_store.upload_artifact.assert_called_once()
        # Should not call list_artifacts when existing_checkpoint is provided
        mock_artifact_store.list_artifacts.assert_not_called()

    def test_update_checkpoint_success_fallback(
        self, checkpoint_repository, mock_artifact_store, temp_checkpoint_dir
    ):
        """Test successful checkpoint update with fallback to list_checkpoint."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "existing123"}]
        }
        mock_artifact_store.upload_artifact.return_value = "existing123"

        success = checkpoint_repository.update_checkpoint(location=temp_checkpoint_dir)

        assert success is True
        mock_artifact_store.list_artifacts.assert_called_once()
        mock_artifact_store.upload_artifact.assert_called_once()

    def test_update_checkpoint_no_existing(self, checkpoint_repository, mock_artifact_store):
        """Test update fails when no existing checkpoint."""
        mock_artifact_store.list_artifacts.return_value = {"artifacts": []}

        success = checkpoint_repository.update_checkpoint()

        assert success is False
        mock_artifact_store.list_artifacts.assert_called_once()
        mock_artifact_store.upload_artifact.assert_not_called()

    def test_retrieve_checkpoint_workflow(self, checkpoint_repository, mock_artifact_store):
        """Test checkpoint retrieval workflow."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the download_artifact to create a test ZIP file
            def mock_download(artifact_id, temp_path):
                with zipfile.ZipFile(temp_path, "w") as zf:
                    zf.writestr("test.txt", "test content")
                    zf.writestr("subdir/nested.txt", "nested content")

            mock_artifact_store.download_artifact.side_effect = mock_download

            checkpoint_repository.retrieve_checkpoint(temp_dir)

            # Verify download_artifact was called with artifact123 and some temp path
            mock_artifact_store.download_artifact.assert_called_once()
            call_args = mock_artifact_store.download_artifact.call_args[0]
            assert call_args[0] == "artifact123"
            assert call_args[1].endswith(".zip")  # Verify temp file has .zip suffix

            # Verify extraction worked correctly - check extracted files exist and have correct content
            extracted_file = os.path.join(temp_dir, "test.txt")
            assert os.path.exists(extracted_file)
            with open(extracted_file, "r") as f:
                assert f.read() == "test content"

            nested_file = os.path.join(temp_dir, "subdir", "nested.txt")
            assert os.path.exists(nested_file)
            with open(nested_file, "r") as f:
                assert f.read() == "nested content"

    def test_retrieve_checkpoint_preserves_empty_directories(
        self, checkpoint_repository, mock_artifact_store
    ):
        """Test checkpoint retrieval preserves empty directories."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the download_artifact to create a ZIP with empty directories
            def mock_download(artifact_id, temp_path):
                with zipfile.ZipFile(temp_path, "w") as zf:
                    zf.writestr("test.txt", "test content")
                    zf.writestr("empty_folder/", "")  # Empty directory
                    zf.writestr("parent/empty_nested/", "")  # Nested empty directory

            mock_artifact_store.download_artifact.side_effect = mock_download

            checkpoint_repository.retrieve_checkpoint(temp_dir)

            # Verify empty directories were created
            assert os.path.exists(os.path.join(temp_dir, "test.txt"))
            assert os.path.isdir(os.path.join(temp_dir, "empty_folder"))
            assert os.path.isdir(os.path.join(temp_dir, "parent"))
            assert os.path.isdir(os.path.join(temp_dir, "parent", "empty_nested"))

    def test_list_checkpoint(self, checkpoint_repository, mock_artifact_store):
        """Test listing checkpoints."""
        expected_artifacts = [{"artifactId": "artifact123"}]
        mock_artifact_store.list_artifacts.return_value = {"artifacts": expected_artifacts}

        result = checkpoint_repository.list_checkpoint()

        assert result == expected_artifacts

    def test_create_zip_from_file(self, checkpoint_repository):
        """Test ZIP creation from single file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as temp_file:
            temp_file.write("test content")
            temp_file_path = temp_file.name

        try:
            zip_content = checkpoint_repository._create_zip_from_path(temp_file_path)

            # Verify ZIP content
            with zipfile.ZipFile(BytesIO(zip_content), "r") as zf:
                assert len(zf.namelist()) == 1
                assert zf.read(zf.namelist()[0]) == b"test content"
        finally:
            os.unlink(temp_file_path)

    def test_create_zip_from_directory(self, checkpoint_repository, temp_checkpoint_dir):
        """Test ZIP creation from directory."""
        zip_content = checkpoint_repository._create_zip_from_path(temp_checkpoint_dir)

        # Verify ZIP content
        with zipfile.ZipFile(BytesIO(zip_content), "r") as zf:
            assert "test.txt" in zf.namelist()
            assert zf.read("test.txt") == b"test content"

    def test_create_zip_includes_empty_directories(self, checkpoint_repository):
        """Test ZIP creation includes empty directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory structure with empty folders
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test content")

            empty_dir = Path(temp_dir) / "empty_folder"
            empty_dir.mkdir()

            # Create nested empty directories
            nested_empty_dir = Path(temp_dir) / "empty_parent" / "empty_nested"
            nested_empty_dir.mkdir(parents=True)

            # Create a non-empty directory (should not have explicit entry)
            non_empty_dir = Path(temp_dir) / "non_empty"
            non_empty_dir.mkdir()
            non_empty_file = non_empty_dir / "file.txt"
            non_empty_file.write_text("content")

            zip_content = checkpoint_repository._create_zip_from_path(temp_dir)

            # Verify ZIP content includes only empty directories explicitly
            with zipfile.ZipFile(BytesIO(zip_content), "r") as zf:
                namelist = zf.namelist()
                assert "test.txt" in namelist
                assert "empty_folder/" in namelist  # Empty directory with trailing slash
                assert "empty_parent/empty_nested/" in namelist  # Nested empty directory
                assert "non_empty/file.txt" in namelist  # File in non-empty directory
                assert (
                    "non_empty/" not in namelist
                )  # Non-empty directory should not have explicit entry

                # Verify file content
                assert zf.read("test.txt") == b"test content"
                assert zf.read("non_empty/file.txt") == b"content"

    def test_create_zip_from_nonexistent_path(self, checkpoint_repository):
        """Test ZIP creation from non-existent path returns None."""
        nonexistent_path = "/path/that/does/not/exist"

        # Should return None instead of creating empty zip
        zip_content = checkpoint_repository._create_zip_from_path(nonexistent_path)

        assert zip_content is None

    def test_create_zip_from_empty_directory(self, checkpoint_repository):
        """Test ZIP creation from empty directory returns None."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty directory
            zip_content = checkpoint_repository._create_zip_from_path(temp_dir)

            assert zip_content is None

    def test_restore_if_available_success(self, checkpoint_repository, mock_artifact_store):
        """Test successful checkpoint restoration."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with patch.object(checkpoint_repository, "retrieve_checkpoint") as mock_retrieve:
            result = checkpoint_repository.restore_if_available()

            assert result is True
            mock_retrieve.assert_called_once_with(checkpoint_repository.checkpoint_location)

    def test_restore_if_available_no_checkpoint(self, checkpoint_repository, mock_artifact_store):
        """Test restoration when no checkpoint exists."""
        mock_artifact_store.list_artifacts.return_value = {"artifacts": []}

        result = checkpoint_repository.restore_if_available()

        assert result is False

    def test_restore_if_available_failure(self, checkpoint_repository, mock_artifact_store):
        """Test restoration handles failures gracefully."""
        mock_artifact_store.list_artifacts.side_effect = Exception("Test error")

        result = checkpoint_repository.restore_if_available()

        assert result is False


class TestRestoreVerification:
    """Test restore verification tracking."""

    def test_restore_verified_false_on_init(self, checkpoint_repository):
        """_restore_verified is False on init."""
        assert checkpoint_repository.is_restore_verified is False

    def test_restore_verified_true_after_successful_restore(
        self, checkpoint_repository, mock_artifact_store
    ):
        """Successful restore sets is_restore_verified to True."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with patch.object(checkpoint_repository, "retrieve_checkpoint"):
            checkpoint_repository.restore_if_available()

        assert checkpoint_repository.is_restore_verified is True

    def test_restore_verified_true_when_no_checkpoint_exists(
        self, checkpoint_repository, mock_artifact_store
    ):
        """Empty checkpoint list sets is_restore_verified to True."""
        mock_artifact_store.list_artifacts.return_value = {"artifacts": []}

        checkpoint_repository.restore_if_available()

        assert checkpoint_repository.is_restore_verified is True

    def test_restore_verified_false_on_list_checkpoint_exception(
        self, checkpoint_repository, mock_artifact_store
    ):
        """list_checkpoint() exception leaves is_restore_verified False."""
        mock_artifact_store.list_artifacts.side_effect = Exception("Auth failed")

        checkpoint_repository.restore_if_available()

        assert checkpoint_repository.is_restore_verified is False

    def test_restore_verified_false_on_retrieve_checkpoint_exception(
        self, checkpoint_repository, mock_artifact_store
    ):
        """retrieve_checkpoint() exception leaves is_restore_verified False."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with patch.object(
            checkpoint_repository, "retrieve_checkpoint", side_effect=Exception("Download failed")
        ):
            checkpoint_repository.restore_if_available()

        assert checkpoint_repository.is_restore_verified is False
