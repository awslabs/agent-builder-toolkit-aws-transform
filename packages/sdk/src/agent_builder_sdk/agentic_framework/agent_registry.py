"""Agent Registry client for ATX platform."""

import json
import logging
import os
import uuid
import zipfile
from typing import List, Optional

from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_sdk.agentic_framework.common import download_from_presigned_url

logger = logging.getLogger(__name__)


class AgentRegistry(AgenticApiHelper):
    """Client for interacting with ATX Agent Registry."""

    def get_agent_skill_names(self, agent_id: str, version: Optional[str] = None) -> List[str]:
        """Get list of skill names from agent's card.

        Args:
            agent_id: The agent identifier
            version: Optional specific version, defaults to latest

        Returns:
            List of skill names, empty list if no skills found
        """
        try:
            request = self._inject_request_context({"name": agent_id})
            if version:
                request["version"] = version

            response = self.client.get_agent_version(**request)

            # Extract agentCard from configuration
            configuration = response.get("configuration", {})
            agent_card_doc = configuration.get("agentCard")

            if not agent_card_doc:
                logger.warning(f"No agentCard found for agent {agent_id}")
                return []

            # Parse agentCard Document (JSON string)
            agent_card = (
                json.loads(agent_card_doc) if isinstance(agent_card_doc, str) else agent_card_doc
            )

            # Extract skill names
            skills = agent_card.get("skills", [])
            return [skill.get("name") for skill in skills if skill.get("name")]

        except Exception as e:
            logger.error(f"Failed to get agent skills for {agent_id}: {e}")
            raise

    def create_download_skill_url(
        self, skill_id: str, idempotency_token: Optional[str] = None
    ) -> dict:
        """Create a presigned URL to download a skill.

        Args:
            skill_id: The skill identifier
            idempotency_token: Optional idempotency token, auto-generated if not provided

        Returns:
            Download URL response with s3preSignedUrl and requestHeaders
        """
        try:
            if idempotency_token is None:
                idempotency_token = str(uuid.uuid4())

            request = self._inject_request_context(
                {"skillName": skill_id, "idempotencyToken": idempotency_token}
            )
            return self.client.create_skill_download_url(**request)
        except Exception as e:
            logger.error(f"Failed to create download URL for skill {skill_id}: {e}")
            raise

    def download_skill(
        self, skill_id: str, destination_dir: str, idempotency_token: Optional[str] = None
    ) -> str:
        """Download and extract skill to destination directory.

        Args:
            skill_id: The skill identifier
            destination_dir: Directory to extract skill contents
            idempotency_token: Optional idempotency token, auto-generated if not provided

        Returns:
            Path to the extracted skill directory

        Raises:
            ValueError: If zip contains path traversal attempts
        """
        try:
            # Create temp file for zip download
            os.makedirs(destination_dir, exist_ok=True)
            zip_path = os.path.join(destination_dir, f"{skill_id}.zip")

            # Download skill zip
            download_response = self.create_download_skill_url(skill_id, idempotency_token)
            download_from_presigned_url(download_response, zip_path)

            # Extract zip with path traversal protection
            skill_dir = os.path.join(destination_dir, skill_id)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Validate all paths before extraction
                for member in zip_ref.namelist():
                    member_path = os.path.join(skill_dir, member)
                    if not os.path.abspath(member_path).startswith(os.path.abspath(skill_dir)):
                        raise ValueError(f"Zip slip attack detected: {member}")
                zip_ref.extractall(skill_dir)

            # Clean up zip file
            os.remove(zip_path)

            logger.info(f"Skill {skill_id} extracted to {skill_dir}")
            return skill_dir

        except Exception as e:
            logger.error(f"Failed to download skill {skill_id}: {e}")
            raise
