# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint repository for agent state/memory/conversation persistence.
"""

import errno
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from agent_builder_sdk.agent_state.agent_state import IAgentState
from agent_builder_sdk.agentic_framework.api_model import CategoryType
from agent_builder_sdk.agentic_framework.artifact_store import ArtifactStore
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.agentic_framework.common import calculate_digest
from agent_builder_sdk.env_var import get_agent_context_from_env, get_max_checkpoints
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_types.type_defs import ArtifactTypeDef

logger = logging.getLogger(__name__)

# Absolute bound on pagination; 100 pages x 100 per page is a generous ceiling.
_MAX_LIST_CHECKPOINT_PAGES = 100

# Multi-checkpoint artifacts carry their write time (ns) in the label, so checkpoints
# that share an artifactCreatedTimestamp still order by recency.
_CHECKPOINT_LABEL_PREFIX = "checkpoint-time-ns-"

# Restore stages inside the destination under this prefix, so every rename stays on one
# filesystem. Entries with the prefix are never moved by a restore or zipped into a checkpoint.
_RESTORE_WORK_PREFIX = ".checkpoint-restore-"

# Rename failures (cross-device, permission, mount point) that fall back to extracting
# over the existing files.
_IN_PLACE_RESTORE_ERRNOS = {errno.EXDEV, errno.EACCES, errno.EPERM, errno.EBUSY}


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
        max_checkpoints: Optional[int] = None,
    ):
        """Initialize CheckpointRepository."""
        self.workspace_id = workspace_id
        self.job_id = job_id
        self.agent_instance_id = agent_instance_id
        self.checkpoint_location = checkpoint_location or self._get_default_location()
        self.auto_check_state_object = auto_check_state_object
        self.max_checkpoints = max_checkpoints
        # Opt-in: retain up to N checkpoints instead of overwriting a single one.
        self.multi_checkpoint_enabled = max_checkpoints is not None and max_checkpoints > 1
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

            # Wall clock: a backwards clock step between two checkpoints that share a
            # created timestamp could misorder them.
            label = None
            if self.multi_checkpoint_enabled:
                label = f"{_CHECKPOINT_LABEL_PREFIX}{time.time_ns()}"

            # Upload checkpoint with artifact_type
            artifact_id = self.artifact_store.upload_artifact(
                content=zip_content,
                digest=digest,
                category_type="STATE",
                file_type="ZIP",
                label=label,
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
                checkpoints = self.list_checkpoint(limit=1)
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

    def retrieve_checkpoint(self, destination_path: str, artifact_id: Optional[str] = None) -> None:
        """Download and extract checkpoint."""
        try:
            logger.info(f"Retrieving checkpoint to {destination_path}")

            if artifact_id is None:
                newest = self._newest_checkpoint()
                if newest is None:
                    logger.info("No checkpoint available to retrieve")
                    return
                artifact_id = newest["artifactId"]

            # Download to temporary file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as temp_file:
                temp_zip_path = temp_file.name
                self.artifact_store.download_artifact(artifact_id, temp_zip_path)
                self._extract_zip_to_path(temp_zip_path, destination_path)

            logger.info(f"Checkpoint retrieved to {destination_path}")

        except Exception:
            logger.exception(f"Failed to retrieve checkpoint to {destination_path}")
            raise

    def _checkpoint_recency_key(self, artifact: ArtifactTypeDef) -> tuple:
        # Created timestamp first; checkpoints sharing it order by the write stamp in
        # their label (multi mode), then artifactId so the order is total.
        created = artifact.get("artifactCreatedTimestamp")
        timestamp = created.timestamp() if created is not None else float("-inf")
        label = artifact.get("artifactLabel") or ""
        stamp = label.removeprefix(_CHECKPOINT_LABEL_PREFIX)
        written_ns = (
            int(stamp) if label.startswith(_CHECKPOINT_LABEL_PREFIX) and stamp.isdecimal() else -1
        )
        return (timestamp, written_ns, artifact.get("artifactId", ""))

    def _select_checkpoint(self, checkpoints: list[ArtifactTypeDef]) -> ArtifactTypeDef:
        return max(checkpoints, key=self._checkpoint_recency_key)

    def _newest_checkpoint(self) -> Optional[ArtifactTypeDef]:
        """The checkpoint a restore uses, or None when there is none."""
        if self.multi_checkpoint_enabled:
            # Checkpoints written close together can share a created timestamp and come
            # back in either order, so rank the retained window instead of one item.
            checkpoints = self.list_restorable_checkpoints()
        else:
            checkpoints = self.list_checkpoint(limit=1)
        return checkpoints[0] if checkpoints else None

    def save_multi_checkpoint(self) -> bool:
        """Append a new checkpoint rather than overwriting the previous one."""
        # No per-artifact delete API; checkpoints beyond max_checkpoints stop being
        # surfaced by list_restorable_checkpoints and remain until their artifactExpiryTimestamp.
        artifact_id = self.create_checkpoint()
        return artifact_id is not None

    def list_restorable_checkpoints(self) -> list[ArtifactTypeDef]:
        """Newest checkpoints first, capped at max_checkpoints.

        Checkpoints that share a created timestamp are ordered by the write time
        recorded in their label, then by artifactId.
        """
        checkpoints = self.list_checkpoint(limit=self.max_checkpoints)
        checkpoints.sort(key=self._checkpoint_recency_key, reverse=True)
        return checkpoints

    def list_checkpoint(self, limit: Optional[int] = None) -> list[ArtifactTypeDef]:
        """STATE checkpoint artifacts for this agent, newest first.

        A page may hold fewer items than requested even when more exist, so this
        keeps paging until limit is met or there is no nextToken.
        """
        try:
            artifacts: list[ArtifactTypeDef] = []
            next_token: Optional[str] = None
            for _ in range(_MAX_LIST_CHECKPOINT_PAGES):
                response = self.artifact_store.list_artifacts(
                    self.agent_instance_id,
                    CategoryType.STATE,
                    next_token=next_token,
                    max_results=limit,
                )
                artifacts.extend(response.get("artifacts", []))
                next_token = response.get("nextToken")
                if limit is not None and len(artifacts) >= limit:
                    artifacts = artifacts[:limit]
                    break
                if not next_token:
                    break
            else:
                logger.error(
                    "list_checkpoint hit page cap %d with more pages remaining; the newest "
                    "checkpoint may be missing",
                    _MAX_LIST_CHECKPOINT_PAGES,
                )
            logger.info(f"Found {len(artifacts)} checkpoint artifacts")
            return artifacts
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
            wall_start = time.perf_counter()
            cpu_start = time.thread_time()
            input_bytes = source.stat().st_size
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.write(source, source.name)
            zip_content = zip_buffer.getvalue()
            size_kb = len(zip_content) / 1024
            logger.info(
                f"Created checkpoint ZIP from file: {size_kb:.2f} KB "
                f"(input: {input_bytes / 1024:.2f} KB, 1 file, "
                f"wall: {time.perf_counter() - wall_start:.3f}s, "
                f"cpu: {time.thread_time() - cpu_start:.3f}s)"
            )
            return zip_content

        elif source.is_dir():
            wall_start = time.perf_counter()
            cpu_start = time.thread_time()

            # Single walk: collect files + empty dirs and compute input size. Writers keep
            # running during a checkpoint, so a file can vanish (e.g. a temp file renamed
            # into place) before it is read; such files are skipped, not fatal.
            files: list[Path] = []
            empty_dirs: list[Path] = []
            input_bytes = 0
            for file_path in source.rglob("*"):
                if file_path.relative_to(source).parts[0].startswith(_RESTORE_WORK_PREFIX):
                    continue
                try:
                    if file_path.is_file():
                        input_bytes += file_path.stat().st_size
                        files.append(file_path)
                    elif file_path.is_dir() and not any(file_path.iterdir()):
                        # Only add empty directories (non-empty ones are implicitly
                        # created by their files).
                        empty_dirs.append(file_path)
                except FileNotFoundError:
                    continue

            zip_buffer = BytesIO()
            written = 0
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in files:
                    try:
                        zip_file.write(file_path, file_path.relative_to(source))
                        written += 1
                    except FileNotFoundError:
                        logger.info(f"Skipping {file_path}: removed while checkpointing")
                for dir_path in empty_dirs:
                    zip_file.writestr(str(dir_path.relative_to(source)) + "/", "")

            if not written:
                logger.warning(
                    f"Directory exists but contains no files, skipping checkpoint: {source_path}"
                )
                return None
            zip_content = zip_buffer.getvalue()
            size_kb = len(zip_content) / 1024
            logger.info(
                f"Created checkpoint ZIP from directory: {size_kb:.2f} KB "
                f"(input: {input_bytes / 1024:.2f} KB, {written} files, "
                f"wall: {time.perf_counter() - wall_start:.3f}s, "
                f"cpu: {time.thread_time() - cpu_start:.3f}s)"
            )
            return zip_content

        else:
            logger.warning(
                f"Source path is neither file nor directory, skipping checkpoint: {source_path}"
            )
            return None

    def _extract_zip_to_path(self, zip_file_path: str, destination_path: str) -> None:
        """Extract ZIP into destination, replacing its contents so it matches the checkpoint.

        Existing entries move to a backup and the extracted ones move in. If a move
        fails, the entries already moved are put back. If the destination is read-only
        or entries can't be renamed at all (cross-device, permission, mount point), the
        ZIP is extracted over the existing files instead, which leaves files absent from
        the checkpoint in place.
        """
        destination = Path(destination_path)
        destination.mkdir(parents=True, exist_ok=True)
        work_dir: Optional[Path] = None
        backed_up: list[str] = []
        placed: list[str] = []
        try:
            # Raises on a read-only destination; its subdirectories may still be writable.
            work_dir = Path(tempfile.mkdtemp(dir=destination, prefix=_RESTORE_WORK_PREFIX))
            staged = work_dir / "staged"
            backup = work_dir / "backup"
            staged.mkdir()
            backup.mkdir()
            with zipfile.ZipFile(zip_file_path, "r") as zip_file:
                zip_file.extractall(staged)
            for entry in list(destination.iterdir()):
                if not entry.name.startswith(_RESTORE_WORK_PREFIX):
                    os.replace(entry, backup / entry.name)
                    backed_up.append(entry.name)
            # os.replace raises on a non-empty name collision instead of nesting into it
            for entry in list(staged.iterdir()):
                os.replace(entry, destination / entry.name)
                placed.append(entry.name)
        except Exception as e:
            if work_dir is not None:
                backup = work_dir / "backup"
                if not self._undo_restore_swap(destination, backup, backed_up, placed):
                    logger.error(f"Restore failed and could not put back all files; kept in {backup}")
                    raise
                shutil.rmtree(work_dir, ignore_errors=True)
            if not (isinstance(e, OSError) and e.errno in _IN_PLACE_RESTORE_ERRNOS):
                raise
            logger.warning(f"Cannot swap {destination} ({e}); extracting over existing files")
            with zipfile.ZipFile(zip_file_path, "r") as zip_file:
                zip_file.extractall(destination)
            return
        shutil.rmtree(work_dir, ignore_errors=True)

    def _undo_restore_swap(
        self, destination: Path, backup: Path, backed_up: list[str], placed: list[str]
    ) -> bool:
        """Remove placed entries and move backed-up ones back; True if all of it worked."""
        ok = True
        for name in placed:
            path = destination / name
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                ok = False
        for name in backed_up:
            try:
                os.replace(backup / name, destination / name)
            except OSError:
                ok = False
        return ok

    def restore_if_available(self) -> bool:
        """Restore checkpoint if available, return True if restored."""
        try:
            newest = self._newest_checkpoint()
            if newest:
                self.retrieve_checkpoint(self.checkpoint_location, artifact_id=newest["artifactId"])
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
        max_checkpoints=get_max_checkpoints(),
    )
