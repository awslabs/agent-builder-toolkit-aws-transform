# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for checkpoint manager.
"""

import errno
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.agent_state.agent_state import IAgentState
from agent_builder_sdk.checkpoint.checkpoint_repository import (
    _CHECKPOINT_LABEL_PREFIX,
    _MAX_LIST_CHECKPOINT_PAGES,
    CheckpointRepository,
    create_checkpoint_repository,
)
from agent_builder_sdk.env_var import MAX_ALLOWED_CHECKPOINTS
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
def multi_checkpoint_repository(mock_artifact_store):
    """Create CheckpointRepository with multi-checkpoint retention enabled."""
    with patch(
        "agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore",
        return_value=mock_artifact_store,
    ):
        return CheckpointRepository("ws1", "job1", "agent1", max_checkpoints=3)


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

    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore")
    @patch("agent_builder_sdk.checkpoint.checkpoint_repository.get_agentic_api_client")
    def test_create_reads_max_checkpoints_from_env(
        self, mock_get_client, mock_artifact_store_class
    ):
        """Factory wires ATX_MAX_CHECKPOINTS into the repository."""
        mock_get_client.return_value = Mock()
        context = AgentRuntimeContext(
            workspace_id="ws",
            job_id="job",
            agent_instance_id="agent",
            initial_auth_token="token",
        )

        with patch.dict(os.environ, {"ATX_MAX_CHECKPOINTS": "4"}, clear=True):
            result = create_checkpoint_repository("/test/path", context)

        assert result.max_checkpoints == 4
        assert result.multi_checkpoint_enabled is True

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

    def test_retrieve_checkpoint_replaces_existing_contents(
        self, checkpoint_repository, mock_artifact_store
    ):
        """Restore replaces the destination: files not in the checkpoint are removed."""
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [{"artifactId": "artifact123"}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            # pre-existing live state that is NOT in the checkpoint
            stale_file = os.path.join(temp_dir, "stale.txt")
            with open(stale_file, "w") as f:
                f.write("stale")
            stale_dir = os.path.join(temp_dir, "stale_dir")
            os.mkdir(stale_dir)

            def mock_download(artifact_id, temp_path):
                with zipfile.ZipFile(temp_path, "w") as zf:
                    zf.writestr("kept.txt", "new content")

            mock_artifact_store.download_artifact.side_effect = mock_download

            checkpoint_repository.retrieve_checkpoint(temp_dir)

            # stale entries are gone and no restore scratch dir is left behind
            assert os.listdir(temp_dir) == ["kept.txt"]

    def test_extract_zip_rolls_back_on_mid_swap_failure(self, checkpoint_repository):
        """A failure while moving staged entries in restores the previous contents."""
        real_replace = os.replace

        with tempfile.TemporaryDirectory() as dest:
            with open(os.path.join(dest, "orig.txt"), "w") as f:
                f.write("orig")

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("a.txt", "a")
                zf.writestr("b.txt", "b")

            def flaky_replace(src, dst):
                if str(src).endswith("b.txt"):
                    raise OSError("disk full")
                return real_replace(src, dst)

            try:
                with patch(
                    "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
                    side_effect=flaky_replace,
                ):
                    with pytest.raises(OSError):
                        checkpoint_repository._extract_zip_to_path(zip_path, dest)

                assert os.listdir(dest) == ["orig.txt"]
            finally:
                os.unlink(zip_path)

    def test_extract_zip_does_not_nest_on_concurrent_dir_recreate(self, checkpoint_repository):
        """A dir recreated during the swap makes the move raise, not nest into it."""
        real_replace = os.replace

        with tempfile.TemporaryDirectory() as dest:
            with open(os.path.join(dest, "keep.txt"), "w") as f:
                f.write("keep")

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("memories/m.json", "{}")

            injected = []

            def racing_replace(src, dst):
                # simulate a concurrent writer recreating memories/ after it was emptied,
                # right as the backed-up entry is moved aside (fires once)
                if str(src).endswith("keep.txt") and not injected:
                    injected.append(True)
                    recreated = os.path.join(dest, "memories")
                    os.makedirs(recreated)
                    with open(os.path.join(recreated, "concurrent.txt"), "w") as f:
                        f.write("racing")
                return real_replace(src, dst)

            try:
                with patch(
                    "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
                    side_effect=racing_replace,
                ):
                    with pytest.raises(OSError):
                        checkpoint_repository._extract_zip_to_path(zip_path, dest)

                assert not os.path.exists(os.path.join(dest, "memories", "memories"))
                assert os.path.exists(os.path.join(dest, "keep.txt"))
            finally:
                os.unlink(zip_path)

    @pytest.mark.parametrize("code", [errno.EXDEV, errno.EACCES, errno.EPERM, errno.EBUSY])
    def test_restore_falls_back_in_place_when_rename_is_refused(
        self,
        checkpoint_repository: CheckpointRepository,
        mock_artifact_store: Mock,
        tmp_path: Path,
        code: int,
    ) -> None:
        """Cross-device, permission or mount-point error on rename: restore lands, is verified."""
        mock_artifact_store.list_artifacts.return_value = {"artifacts": [{"artifactId": "cp"}]}

        def mock_download(artifact_id: str, temp_path: str) -> None:
            with zipfile.ZipFile(temp_path, "w") as zf:
                zf.writestr("state.json", "restored")

        mock_artifact_store.download_artifact.side_effect = mock_download
        (tmp_path / "live.txt").write_text("live")
        (tmp_path / "state.json").write_text("old")
        checkpoint_repository.checkpoint_location = str(tmp_path)

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=OSError(code, os.strerror(code)),
        ), patch("agent_builder_sdk.checkpoint.checkpoint_repository.logger") as mock_logger:
            assert checkpoint_repository.restore_if_available() is True

        assert checkpoint_repository.is_restore_verified is True
        assert (tmp_path / "state.json").read_text() == "restored"
        # extracted over existing files: nothing lost, no scratch dir left
        assert sorted(os.listdir(tmp_path)) == ["live.txt", "state.json"]
        # the warning is the only signal that stale files were left in place
        (warning,) = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert str(tmp_path) in warning and os.strerror(code) in warning
        assert "extracting over existing files" in warning

    def test_in_place_restore_that_fails_partway_raises(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A failed in-place extract is raised; the files before the failure stay restored."""
        dest = tmp_path / "dest"
        (dest / "ro").mkdir(parents=True)
        (dest / "aaa.json").write_text("old")
        (dest / "state.json").write_text("old")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("aaa.json", "restored")
            zf.writestr("ro/new.txt", "restored")
            zf.writestr("state.json", "restored")

        (dest / "ro").chmod(0o555)
        try:
            with pytest.raises(PermissionError):
                checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))
        finally:
            (dest / "ro").chmod(0o755)

        assert (dest / "aaa.json").read_text() == "restored"
        assert (dest / "state.json").read_text() == "old"
        assert sorted(os.listdir(dest)) == ["aaa.json", "ro", "state.json"]

    def test_undo_puts_back_entry_recreated_during_swap(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A writer recreating a backed-up directory mid-swap does not strand the original."""
        dest = tmp_path / "dest"
        (dest / "memories").mkdir(parents=True)
        (dest / "memories" / "old1.json").write_text("1")
        (dest / "memories" / "old2.json").write_text("2")
        (dest / "keep.txt").write_text("keep")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("memories/m.json", "{}")

        real_replace = os.replace
        recreated = []

        def replace_after_writer_recreates(src: Path, dst: Path) -> None:
            if not recreated and not (dest / "memories").exists():
                recreated.append(True)
                (dest / "memories").mkdir()
                (dest / "memories" / "concurrent.json").write_text("racing")
            return real_replace(src, dst)

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=replace_after_writer_recreates,
        ):
            with pytest.raises(OSError) as raised:
                checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        assert raised.value.errno == errno.ENOTEMPTY
        restored = {str(p.relative_to(dest)): p.read_text() for p in dest.rglob("*") if p.is_file()}
        assert restored == {"keep.txt": "keep", "memories/old1.json": "1", "memories/old2.json": "2"}

    def test_completed_restore_removes_backup_with_read_only_directory(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A read-only directory inside a replaced entry does not strand the backup."""
        dest = tmp_path / "dest"
        (dest / "cache" / "sub").mkdir(parents=True)
        (dest / "cache" / "sub" / "module.bin").write_text("x")
        (dest / "cache" / "sub").chmod(0o555)
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        assert os.listdir(dest) == ["new.txt"]

    def test_work_dir_that_cannot_be_removed_is_logged(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """The restore still completes; the leftover path and its cause are in a warning."""
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.shutil.rmtree",
            side_effect=OSError(errno.EBUSY, os.strerror(errno.EBUSY)),
        ), patch("agent_builder_sdk.checkpoint.checkpoint_repository.logger") as mock_logger:
            checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        (work_dir,) = dest.glob(".checkpoint-restore-*")
        assert (dest / "new.txt").read_text() == "new"
        (warning,) = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert str(work_dir) in warning and os.strerror(errno.EBUSY) in warning

    def test_restore_into_read_only_dir_with_writable_subdirs(
        self, checkpoint_repository: CheckpointRepository, mock_artifact_store: Mock, tmp_path: Path
    ) -> None:
        """No room to stage in a read-only checkpoint dir: extract in place, restore verified."""
        mock_artifact_store.list_artifacts.return_value = {"artifacts": [{"artifactId": "cp"}]}

        def mock_download(artifact_id: str, temp_path: str) -> None:
            with zipfile.ZipFile(temp_path, "w") as zf:
                zf.writestr("agent/conv.json", "restored")
                zf.writestr("queue/requests.json", "[]")

        mock_artifact_store.download_artifact.side_effect = mock_download
        (tmp_path / "agent").mkdir()
        (tmp_path / "queue").mkdir()
        (tmp_path / "agent" / "conv.json").write_text("live")
        checkpoint_repository.checkpoint_location = str(tmp_path)

        tmp_path.chmod(0o555)
        try:
            assert checkpoint_repository.restore_if_available() is True
        finally:
            tmp_path.chmod(0o755)

        assert checkpoint_repository.is_restore_verified is True
        assert (tmp_path / "agent" / "conv.json").read_text() == "restored"
        assert (tmp_path / "queue" / "requests.json").read_text() == "[]"
        assert sorted(os.listdir(tmp_path)) == ["agent", "queue"]

    def test_restore_under_read_only_parent_replaces_contents(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """The swap stages inside the destination, so it needs no write access to the parent."""
        parent = tmp_path / "parent"
        dest = parent / "state"
        dest.mkdir(parents=True)
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("state.json", "restored")

        parent.chmod(0o555)
        try:
            checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))
        finally:
            parent.chmod(0o755)

        assert {p.name: p.read_text() for p in dest.iterdir()} == {"state.json": "restored"}

    def test_extract_zip_failure_mid_backup_keeps_every_live_file(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A rename failing partway through moving live entries aside loses none of them."""
        dest = tmp_path / "dest"
        dest.mkdir()
        live = {f"live{i}.txt": f"live {i}" for i in range(5)}
        for name, text in live.items():
            (dest / name).write_text(text)
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        real_replace = os.replace
        calls = []

        def fail_third_move(src: Path, dst: Path) -> None:
            calls.append(src)
            if len(calls) == 3:
                raise OSError(errno.EIO, "I/O error")
            return real_replace(src, dst)

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=fail_third_move,
        ):
            with pytest.raises(OSError):
                checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        assert {p.name: p.read_text() for p in dest.iterdir()} == live

    def test_extract_zip_keeps_backup_when_put_back_fails(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """If live entries can't be moved back either, they stay in the backup dir, path logged."""
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        real_replace = os.replace

        def only_moves_aside(src: Path, dst: Path) -> None:
            if Path(src).parent == dest:
                return real_replace(src, dst)
            raise OSError(errno.EIO, "I/O error")

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=only_moves_aside,
        ), patch("agent_builder_sdk.checkpoint.checkpoint_repository.logger") as mock_logger:
            with pytest.raises(OSError):
                checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        kept = list(dest.glob(".checkpoint-restore-*/backup/live.txt"))
        assert [p.read_text() for p in kept] == ["live"]
        assert str(kept[0].parent) in mock_logger.error.call_args[0][0]
        # the extracted copy can be downloaded again, so only the backup is kept
        assert os.listdir(kept[0].parent.parent) == ["backup"]

    def test_failed_undo_logs_each_entry_and_cause(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """Each entry the undo could not remove or put back is logged with its error."""
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.txt", "a")
            zf.writestr("b.txt", "b")

        real_replace = os.replace
        placed = []

        def second_placement_and_put_back_fail(src: Path, dst: Path) -> None:
            step = Path(src).parent.name
            if step == "backup":
                raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
            if step == "staged":
                placed.append(Path(src).name)
                if len(placed) == 2:
                    raise OSError(errno.EIO, os.strerror(errno.EIO))
            return real_replace(src, dst)

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=second_placement_and_put_back_fail,
        ), patch.object(
            Path, "unlink", side_effect=OSError(errno.EBUSY, os.strerror(errno.EBUSY))
        ), patch("agent_builder_sdk.checkpoint.checkpoint_repository.logger") as mock_logger:
            with pytest.raises(OSError):
                checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        errors = [call.args[0] for call in mock_logger.error.call_args_list]
        assert any(
            str(dest / placed[0]) in line and os.strerror(errno.EBUSY) in line for line in errors
        )
        assert any("live.txt" in line and os.strerror(errno.ENOSPC) in line for line in errors)

    def test_completed_restore_removes_backup_kept_by_failed_restore(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A restore that replaces the directory supersedes what an earlier one stranded."""
        dest = tmp_path / "dest"
        stranded = dest / ".checkpoint-restore-earlier" / "backup" / "stranded.txt"
        stranded.parent.mkdir(parents=True)
        stranded.write_text("stranded")
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        assert os.listdir(dest) == ["new.txt"]

    def test_in_place_restore_keeps_backup_kept_by_failed_restore(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """Extracting over existing files replaces nothing, so a stranded file is still needed."""
        dest = tmp_path / "dest"
        stranded = dest / ".checkpoint-restore-earlier" / "backup" / "stranded.txt"
        stranded.parent.mkdir(parents=True)
        stranded.write_text("stranded")
        (dest / "live.txt").write_text("live")
        zip_path = tmp_path / "cp.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("new.txt", "new")

        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.os.replace",
            side_effect=OSError(errno.EXDEV, "Invalid cross-device link"),
        ):
            checkpoint_repository._extract_zip_to_path(str(zip_path), str(dest))

        assert stranded.read_text() == "stranded"
        assert sorted(os.listdir(dest)) == [".checkpoint-restore-earlier", "live.txt", "new.txt"]

    def test_create_zip_skips_restore_scratch_dir(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A backup kept by a failed restore is never uploaded as agent state."""
        (tmp_path / "state.json").write_text("{}")
        kept = tmp_path / ".checkpoint-restore-abc" / "backup"
        kept.mkdir(parents=True)
        (kept / "old.json").write_text("{}")

        zip_content = checkpoint_repository._create_zip_from_path(str(tmp_path))

        assert zipfile.ZipFile(BytesIO(zip_content)).namelist() == ["state.json"]

    def test_create_zip_skips_file_removed_mid_checkpoint(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A file renamed away between the walk and its read is skipped, not fatal."""
        (tmp_path / "requests.json").write_text("[]")
        (tmp_path / "requests.tmp").write_text("[1]")
        real_write = zipfile.ZipFile.write

        def write_after_writer_renames(
            self: zipfile.ZipFile, filename: Path, *args: Any, **kwargs: Any
        ) -> None:
            if Path(filename).name == "requests.tmp":
                os.replace(filename, tmp_path / "requests.json")  # the writer's tmp + rename
            return real_write(self, filename, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "write", write_after_writer_renames):
            zip_content = checkpoint_repository._create_zip_from_path(str(tmp_path))

        assert zipfile.ZipFile(BytesIO(zip_content)).namelist() == ["requests.json"]

    def test_create_zip_returns_none_when_every_file_is_removed_mid_checkpoint(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """No file left to write means no checkpoint, not an empty ZIP that a restore applies."""
        (tmp_path / "requests.tmp").write_text("[1]")
        real_write = zipfile.ZipFile.write

        def write_after_writer_removes(
            self: zipfile.ZipFile, filename: Path, *args: Any, **kwargs: Any
        ) -> None:
            os.unlink(filename)
            return real_write(self, filename, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "write", write_after_writer_removes):
            assert checkpoint_repository._create_zip_from_path(str(tmp_path)) is None

    def test_create_zip_skips_file_removed_during_walk(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A file renamed away after the walk listed it, before its size is read, is skipped."""
        (tmp_path / "requests.json").write_text("[]")
        (tmp_path / "requests.tmp").write_text("[1]")
        real_is_file = Path.is_file

        def is_file_then_writer_renames(self: Path) -> bool:
            result = real_is_file(self)
            if self.name == "requests.tmp":
                os.replace(self, tmp_path / "requests.json")
            return result

        with patch.object(Path, "is_file", is_file_then_writer_renames):
            zip_content = checkpoint_repository._create_zip_from_path(str(tmp_path))

        assert zipfile.ZipFile(BytesIO(zip_content)).namelist() == ["requests.json"]

    def test_create_zip_skips_directory_removed_during_walk(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """Directories removed after their parent was listed are skipped, not fatal."""
        for name in ("a", "b", "c"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "file.txt").write_text(name)
        real_is_file = Path.is_file

        def is_file_while_writer_removes_other_dirs(self: Path) -> bool:
            if self.parent.parent == tmp_path:
                for other in tmp_path.iterdir():
                    if other != self.parent:
                        shutil.rmtree(other)
            return real_is_file(self)

        with patch.object(Path, "is_file", is_file_while_writer_removes_other_dirs):
            zip_content = checkpoint_repository._create_zip_from_path(str(tmp_path))

        (survivor,) = tmp_path.iterdir()
        assert zipfile.ZipFile(BytesIO(zip_content)).namelist() == [f"{survivor.name}/file.txt"]

    def test_create_zip_raises_when_directory_listing_fails(
        self, checkpoint_repository: CheckpointRepository, tmp_path: Path
    ) -> None:
        """A directory that exists but cannot be listed fails the checkpoint.

        Skipping it would produce a ZIP without that subtree.
        """
        for name in ("agent", "queue"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "file.txt").write_text(name)
        real_iterdir = Path.iterdir
        real_scandir = os.scandir
        probed: list[Path] = []

        def iterdir_then_record(self: Path) -> Iterator[Path]:
            entries = list(real_iterdir(self))
            probed.append(self)
            return iter(entries)

        def scandir_fails_once_probed(path: Any) -> Any:
            if Path(path) in probed:
                raise OSError(errno.EIO, os.strerror(errno.EIO), str(path))
            return real_scandir(path)

        with (
            patch.object(Path, "iterdir", iterdir_then_record),
            patch("os.scandir", scandir_fails_once_probed),
            pytest.raises(OSError) as raised,
        ):
            checkpoint_repository._create_zip_from_path(str(tmp_path))

        assert raised.value.errno == errno.EIO

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
            mock_retrieve.assert_called_once_with(
                checkpoint_repository.checkpoint_location, artifact_id="artifact123"
            )
            # single paginated pass, not two
            assert mock_artifact_store.list_artifacts.call_count == 1

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


def _ts(artifact_id: str, epoch: int) -> dict:
    return {
        "artifactId": artifact_id,
        "artifactCreatedTimestamp": datetime.fromtimestamp(epoch, tz=timezone.utc),
    }


def _stamped(artifact_id: str, epoch: int, written_ns: int) -> dict:
    return {**_ts(artifact_id, epoch), "artifactLabel": f"{_CHECKPOINT_LABEL_PREFIX}{written_ns}"}


class TestMultiCheckpoint:
    """Test opt-in multi-checkpoint retention."""

    def test_single_mode_disabled_by_default(self, checkpoint_repository):
        assert checkpoint_repository.multi_checkpoint_enabled is False
        assert checkpoint_repository.max_checkpoints is None

    def test_multi_mode_enabled(self, multi_checkpoint_repository):
        assert multi_checkpoint_repository.multi_checkpoint_enabled is True
        assert multi_checkpoint_repository.max_checkpoints == 3

    def test_max_checkpoints_one_stays_single_mode(self, mock_artifact_store):
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore",
            return_value=mock_artifact_store,
        ):
            repo = CheckpointRepository("ws1", "job1", "agent1", max_checkpoints=1)
        assert repo.multi_checkpoint_enabled is False

    def test_save_multi_checkpoint_appends(self, multi_checkpoint_repository):
        with patch.object(
            multi_checkpoint_repository, "create_checkpoint", return_value="artifact123"
        ) as mock_create:
            result = multi_checkpoint_repository.save_multi_checkpoint()

        assert result is True
        mock_create.assert_called_once_with()

    def test_save_multi_checkpoint_returns_false_when_create_fails(
        self, multi_checkpoint_repository
    ):
        with patch.object(multi_checkpoint_repository, "create_checkpoint", return_value=None):
            assert multi_checkpoint_repository.save_multi_checkpoint() is False

    def test_select_checkpoint_newest_in_multi_mode(self, multi_checkpoint_repository):
        checkpoints = [_ts("old", 1), _ts("new", 3), _ts("mid", 2)]

        selected = multi_checkpoint_repository._select_checkpoint(checkpoints)

        assert selected["artifactId"] == "new"

    def test_select_checkpoint_same_second_picks_later_write(
        self, multi_checkpoint_repository: CheckpointRepository
    ) -> None:
        # Same created timestamp; artifactId order is the reverse of write order.
        earlier, later = _stamped("z-earlier", 5, 100), _stamped("a-later", 5, 200)

        for listed in ([earlier, later], [later, earlier]):
            assert multi_checkpoint_repository._select_checkpoint(listed)["artifactId"] == "a-later"

    def test_create_checkpoint_stamps_write_time_in_multi_mode(
        self,
        multi_checkpoint_repository: CheckpointRepository,
        mock_artifact_store: Mock,
        temp_checkpoint_dir: str,
    ) -> None:
        before = time.time_ns()

        multi_checkpoint_repository.create_checkpoint(temp_checkpoint_dir)

        label = mock_artifact_store.upload_artifact.call_args.kwargs["label"]
        assert label.startswith("checkpoint-time-ns-")
        assert int(label.removeprefix("checkpoint-time-ns-")) >= before

    def test_create_checkpoint_sends_no_label_in_single_mode(
        self,
        checkpoint_repository: CheckpointRepository,
        mock_artifact_store: Mock,
        temp_checkpoint_dir: str,
    ) -> None:
        checkpoint_repository.create_checkpoint(temp_checkpoint_dir)

        assert mock_artifact_store.upload_artifact.call_args.kwargs["label"] is None

    def test_select_checkpoint_same_second_tiebreak_by_artifact_id(
        self, multi_checkpoint_repository
    ):
        checkpoints = [_ts("a", 5), _ts("z", 5), _ts("m", 5)]

        selected = multi_checkpoint_repository._select_checkpoint(checkpoints)

        assert selected["artifactId"] == "z"

    def test_select_checkpoint_newest_in_single_mode(self, checkpoint_repository):
        # single mode also selects by recency now, so a downgrade cannot pick a stale artifact
        checkpoints = [_ts("first", 1), _ts("second", 3)]

        selected = checkpoint_repository._select_checkpoint(checkpoints)

        assert selected["artifactId"] == "second"

    def test_list_restorable_checkpoints_sorted_and_capped(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        # Store returns newest first.
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [_ts("c4", 4), _ts("c3", 3), _ts("c2", 2), _ts("c1", 1)]
        }

        result = multi_checkpoint_repository.list_restorable_checkpoints()

        assert [c["artifactId"] for c in result] == ["c4", "c3", "c2"]
        assert mock_artifact_store.list_artifacts.call_args.kwargs["max_results"] == 3

    def test_restore_checkpoint_by_id(self, multi_checkpoint_repository, mock_artifact_store):
        mock_artifact_store.list_artifacts.return_value = {"artifacts": [_ts("artifact123", 1)]}
        with patch.object(multi_checkpoint_repository, "retrieve_checkpoint") as mock_retrieve:
            multi_checkpoint_repository.restore_checkpoint("artifact123", "/dest")

        mock_retrieve.assert_called_once_with("/dest", "artifact123")
        assert multi_checkpoint_repository.is_restore_verified is True

    def test_restore_checkpoint_rejects_unknown_id(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        mock_artifact_store.list_artifacts.return_value = {"artifacts": [_ts("known", 1)]}
        with patch.object(multi_checkpoint_repository, "retrieve_checkpoint") as mock_retrieve:
            with pytest.raises(ValueError):
                multi_checkpoint_repository.restore_checkpoint("unknown")

        mock_retrieve.assert_not_called()
        assert multi_checkpoint_repository.is_restore_verified is False

    def test_retrieve_checkpoint_with_explicit_id_skips_list(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        with tempfile.TemporaryDirectory() as temp_dir:

            def mock_download(artifact_id, temp_path):
                with zipfile.ZipFile(temp_path, "w") as zf:
                    zf.writestr("test.txt", "content")

            mock_artifact_store.download_artifact.side_effect = mock_download

            multi_checkpoint_repository.retrieve_checkpoint(temp_dir, artifact_id="explicit-id")

        mock_artifact_store.list_artifacts.assert_not_called()
        assert mock_artifact_store.download_artifact.call_args[0][0] == "explicit-id"

    def test_restore_if_available_picks_newest_in_multi_mode(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        # Store returns newest first.
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [_ts("new", 5), _ts("old", 1)]
        }

        with tempfile.TemporaryDirectory() as temp_dir:

            def mock_download(artifact_id, temp_path):
                with zipfile.ZipFile(temp_path, "w") as zf:
                    zf.writestr("test.txt", "content")

            mock_artifact_store.download_artifact.side_effect = mock_download
            multi_checkpoint_repository.checkpoint_location = temp_dir

            assert multi_checkpoint_repository.restore_if_available() is True

        assert mock_artifact_store.download_artifact.call_args[0][0] == "new"

    def test_restore_if_available_same_second_restores_later_write(
        self,
        multi_checkpoint_repository: CheckpointRepository,
        mock_artifact_store: Mock,
        tmp_path: Path,
    ) -> None:
        # A same-second pair can come back in either order, so restore ranks the retained
        # window rather than trusting the first item.
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [_stamped("z-earlier", 5, 100), _stamped("a-later", 5, 200)]
        }

        def mock_download(artifact_id: str, temp_path: str) -> None:
            with zipfile.ZipFile(temp_path, "w") as zf:
                zf.writestr("test.txt", artifact_id)

        mock_artifact_store.download_artifact.side_effect = mock_download
        multi_checkpoint_repository.checkpoint_location = str(tmp_path)

        assert multi_checkpoint_repository.restore_if_available() is True

        assert mock_artifact_store.list_artifacts.call_args.kwargs["max_results"] == 3
        assert (tmp_path / "test.txt").read_text() == "a-later"

    def test_list_checkpoint_paginates_all_pages(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        mock_artifact_store.list_artifacts.side_effect = [
            {"artifacts": [_ts("a", 1), _ts("b", 2)], "nextToken": "tok"},
            {"artifacts": [_ts("c", 3)]},
        ]

        result = multi_checkpoint_repository.list_checkpoint()

        assert [c["artifactId"] for c in result] == ["a", "b", "c"]
        assert mock_artifact_store.list_artifacts.call_count == 2
        assert mock_artifact_store.list_artifacts.call_args_list[1].kwargs["next_token"] == "tok"

    def test_select_newest_across_pages(self, multi_checkpoint_repository, mock_artifact_store):
        mock_artifact_store.list_artifacts.side_effect = [
            {"artifacts": [_ts("p1", 1)], "nextToken": "t"},
            {"artifacts": [_ts("p2", 9)]},
        ]

        result = multi_checkpoint_repository.list_restorable_checkpoints()

        assert result[0]["artifactId"] == "p2"

    def test_list_checkpoint_stops_at_absolute_page_cap(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        # nextToken never clears; loop must stop at the absolute cap and log an error
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [_ts("a", 1)],
            "nextToken": "t",
        }

        with patch("agent_builder_sdk.checkpoint.checkpoint_repository.logger") as mock_logger:
            result = multi_checkpoint_repository.list_checkpoint()

        assert mock_artifact_store.list_artifacts.call_count == _MAX_LIST_CHECKPOINT_PAGES
        assert len(result) == _MAX_LIST_CHECKPOINT_PAGES
        mock_logger.error.assert_called_once()

    def test_list_checkpoint_stops_early_when_limit_reached(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        # nextToken present but limit met, so no further calls.
        mock_artifact_store.list_artifacts.return_value = {
            "artifacts": [_ts("n1", 5), _ts("n2", 4), _ts("n3", 3), _ts("n4", 2)],
            "nextToken": "more",
        }

        result = multi_checkpoint_repository.list_checkpoint(limit=3)

        assert [c["artifactId"] for c in result] == ["n1", "n2", "n3"]
        assert mock_artifact_store.list_artifacts.call_count == 1
        assert mock_artifact_store.list_artifacts.call_args.kwargs["max_results"] == 3

    def test_list_checkpoint_pages_until_limit_filled(
        self, multi_checkpoint_repository, mock_artifact_store
    ):
        # A page can be short even when more exist, so page until limit met.
        mock_artifact_store.list_artifacts.side_effect = [
            {"artifacts": [_ts("n1", 5)], "nextToken": "t"},
            {"artifacts": [_ts("n2", 4)], "nextToken": "t2"},
        ]

        result = multi_checkpoint_repository.list_checkpoint(limit=2)

        assert [c["artifactId"] for c in result] == ["n1", "n2"]
        assert mock_artifact_store.list_artifacts.call_count == 2

    def test_list_checkpoint_requests_pages_of_at_most_100(
        self, multi_checkpoint_repository: CheckpointRepository, mock_artifact_store: Mock
    ) -> None:
        # ListArtifacts accepts maxResults up to 100, so a larger limit is filled across pages.
        mock_artifact_store.list_artifacts.side_effect = [
            {"artifacts": [_ts(f"p{page}-{i}", 1) for i in range(100)], "nextToken": "more"}
            for page in range(3)
        ]

        result = multi_checkpoint_repository.list_checkpoint(limit=250)

        assert len(result) == 250
        page_sizes = [
            call.kwargs["max_results"] for call in mock_artifact_store.list_artifacts.call_args_list
        ]
        assert page_sizes == [100, 100, 100]

    def test_max_checkpoints_above_cap_is_clamped(self, mock_artifact_store: Mock) -> None:
        with patch(
            "agent_builder_sdk.checkpoint.checkpoint_repository.ArtifactStore",
            return_value=mock_artifact_store,
        ):
            repo = CheckpointRepository("ws1", "job1", "agent1", max_checkpoints=500)

        assert repo.max_checkpoints == MAX_ALLOWED_CHECKPOINTS
        assert repo.multi_checkpoint_enabled is True
