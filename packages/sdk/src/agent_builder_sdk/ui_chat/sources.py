"""Source citations for ATX chat UI.

Builds ``atx-sources`` fenced code blocks that the chat frontend renders as a
collapsible "Sources (N)" widget with download links.

Usage:

    from agent_builder_sdk.ui_chat.sources import Sources

    # workspace_id and job_id are read from env vars automatically
    sources = Sources()
    sources.add_artifact_source(
        title="servers.csv",
        artifact_id="abc-123",
        description="83 decisions traced",
    )
    message_text = f"{agent_response}\\n\\n{sources.build()}"

The frontend strips the fenced block before rendering markdown and passes the
JSON payload to ``SourceRenderer`` which displays each entry as a downloadable
link using the ``aws-transform://`` deeplink scheme.

See: https://quip-amazon.com/yssKApcGR6qi
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass

from agent_builder_sdk.env_var import ENV_KEY_JOB_ID, ENV_KEY_WORKSPACE_ID

logger = logging.getLogger(__name__)

BLOCK_TAG = "atx-sources"


def _validate_uuid(value: str, name: str) -> None:
    """Validate that a string is a valid UUID."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValueError(f"{name} must be a valid UUID, got: {value}")


@dataclass
class SourceEntry:
    """A single source citation entry."""

    id: str
    title: str
    link: str
    description: str = ""

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "title": self.title, "link": self.link}
        if self.description:
            d["description"] = self.description
        return d


class Sources:
    """Builder for atx-sources fenced code blocks.

    Collects source entries and serializes them into a fenced code block
    that the ATX chat UI renders as a collapsible sources widget.

    workspace_id and job_id are read from WORKSPACE_ID and JOB_ID environment
    variables. They can also be provided explicitly to the constructor.
    """

    def __init__(self, workspace_id: str | None = None, job_id: str | None = None):
        self._workspace_id = workspace_id or os.environ[ENV_KEY_WORKSPACE_ID]
        self._job_id = job_id or os.environ[ENV_KEY_JOB_ID]
        _validate_uuid(self._workspace_id, "workspace_id")
        _validate_uuid(self._job_id, "job_id")
        self._entries: list[SourceEntry] = []

    def add_artifact_source(
        self,
        title: str,
        artifact_id: str,
        description: str = "",
    ) -> "Sources":
        """Add a source backed by an ATX artifact.

        Args:
            title: Display title shown in the sources widget.
            artifact_id: The artifact ID used in the deeplink path.
            description: Optional description shown below the title.

        Returns:
            self for chaining.

        Raises:
            ValueError: If artifact_id is not a valid UUID.
        """
        _validate_uuid(artifact_id, "artifact_id")
        entry_id = str(uuid.uuid4())
        link = (
            f"aws-transform://workspaces/{self._workspace_id}"
            f"/jobs/{self._job_id}/artifacts/{artifact_id}"
        )
        self._entries.append(
            SourceEntry(id=entry_id, title=title, link=link, description=description)
        )
        return self

    def build(self) -> str:
        """Serialize all entries into an atx-sources fenced code block.

        Returns:
            A markdown fenced code block string, or empty string if no entries.
        """
        if not self._entries:
            return ""

        payload = json.dumps([e.to_dict() for e in self._entries], separators=(",", ":"))
        return f"```{BLOCK_TAG}\n{payload}\n```"
