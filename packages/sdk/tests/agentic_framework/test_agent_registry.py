# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
import zipfile
from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.agent_registry import AgentRegistry


@pytest.fixture
def agent_registry(monkeypatch):
    """Test fixture for AgentRegistry."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("ATX_AUTHZ_TOKEN=test-token")
        auth_file_path = f.name

    monkeypatch.setenv("AUTH_TOKEN_FILE", auth_file_path)

    mock_client = mock.Mock()
    return AgentRegistry(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        client=mock_client,
    )


class TestGetAgentSkillNames:
    """Test cases for get_agent_skill_names method."""

    def test_get_agent_skill_names_success(self, agent_registry):
        """Test successful retrieval of skill names."""
        expected_response = {
            "configuration": {
                "agentCard": {
                    "skills": [
                        {"name": "skill-1"},
                        {"name": "skill-2"},
                    ]
                }
            }
        }
        agent_registry.client.get_agent_version.return_value = expected_response

        result = agent_registry.get_agent_skill_names("test-agent", "1.0")

        assert result == ["skill-1", "skill-2"]
        call_args = agent_registry.client.get_agent_version.call_args[1]
        assert call_args["name"] == "test-agent"
        assert call_args["version"] == "1.0"

    def test_get_agent_skill_names_no_skills(self, agent_registry):
        """Test when agent has no skills."""
        expected_response = {"configuration": {"agentCard": {"skills": []}}}
        agent_registry.client.get_agent_version.return_value = expected_response

        result = agent_registry.get_agent_skill_names("test-agent", "1.0")

        assert result == []


class TestCreateDownloadSkillUrl:
    """Test cases for create_download_skill_url method."""

    def test_create_download_skill_url_with_token(self, agent_registry):
        """Test creating download URL with provided idempotency token."""
        expected_response = {
            "s3PreSignedUrl": "https://s3.amazonaws.com/...",
            "s3UrlExpiryTimestamp": 1234567890,
            "requestHeaders": {"host": ["s3.amazonaws.com"]},
        }
        agent_registry.client.create_skill_download_url.return_value = expected_response

        result = agent_registry.create_download_skill_url("test-skill", "my-token")

        assert result == expected_response
        call_args = agent_registry.client.create_skill_download_url.call_args[1]
        assert call_args["skillName"] == "test-skill"
        assert call_args["idempotencyToken"] == "my-token"
        assert "requestContext" in call_args

    def test_create_download_skill_url_auto_token(self, agent_registry):
        """Test creating download URL with auto-generated idempotency token."""
        expected_response = {
            "s3PreSignedUrl": "https://s3.amazonaws.com/...",
            "s3UrlExpiryTimestamp": 1234567890,
            "requestHeaders": {"host": ["s3.amazonaws.com"]},
        }
        agent_registry.client.create_skill_download_url.return_value = expected_response

        result = agent_registry.create_download_skill_url("test-skill")

        assert result == expected_response
        call_args = agent_registry.client.create_skill_download_url.call_args[1]
        assert call_args["skillName"] == "test-skill"
        assert "idempotencyToken" in call_args
        assert len(call_args["idempotencyToken"]) == 36  # UUID length


class TestDownloadSkill:
    """Test cases for download_skill method."""

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_registry.download_from_presigned_url"
    )
    def test_download_skill_success(self, mock_download, agent_registry):
        """Test successful skill download and extraction."""
        # Setup
        download_response = {
            "s3PreSignedUrl": "https://s3.amazonaws.com/...",
            "requestHeaders": {"host": ["s3.amazonaws.com"]},
        }
        agent_registry.client.create_skill_download_url.return_value = download_response

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock zip file in a separate location
            zip_source = os.path.join(temp_dir, "source.zip")
            with zipfile.ZipFile(zip_source, "w") as zf:
                zf.writestr("SKILL.md", "# Test Skill")

            # Mock download to copy from source to destination
            def mock_download_impl(response, dest_path):
                import shutil

                shutil.copy(zip_source, dest_path)

            mock_download.side_effect = mock_download_impl

            # Execute
            result = agent_registry.download_skill("test-skill", temp_dir, "my-token")

            # Verify
            assert result == os.path.join(temp_dir, "test-skill")
            assert os.path.exists(result)
            assert os.path.exists(os.path.join(result, "SKILL.md"))
            assert not os.path.exists(os.path.join(temp_dir, "test-skill.zip"))  # Cleaned up

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_registry.download_from_presigned_url"
    )
    def test_download_skill_auto_token(self, mock_download, agent_registry):
        """Test skill download with auto-generated idempotency token."""
        download_response = {
            "s3PreSignedUrl": "https://s3.amazonaws.com/...",
            "requestHeaders": {"host": ["s3.amazonaws.com"]},
        }
        agent_registry.client.create_skill_download_url.return_value = download_response

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock zip file in a separate location
            zip_source = os.path.join(temp_dir, "source.zip")
            with zipfile.ZipFile(zip_source, "w") as zf:
                zf.writestr("SKILL.md", "# Test Skill")

            def mock_download_impl(response, dest_path):
                import shutil

                shutil.copy(zip_source, dest_path)

            mock_download.side_effect = mock_download_impl

            result = agent_registry.download_skill("test-skill", temp_dir)

            assert result == os.path.join(temp_dir, "test-skill")
            call_args = agent_registry.client.create_skill_download_url.call_args[1]
            assert "idempotencyToken" in call_args

    @mock.patch(
        "agent_builder_sdk.agentic_framework.agent_registry.download_from_presigned_url"
    )
    def test_download_skill_zip_slip_protection(self, mock_download, agent_registry):
        """Test that zip slip attacks are prevented."""
        download_response = {
            "s3PreSignedUrl": "https://s3.amazonaws.com/...",
            "requestHeaders": {"host": ["s3.amazonaws.com"]},
        }
        agent_registry.client.create_skill_download_url.return_value = download_response

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a malicious zip with path traversal
            zip_source = os.path.join(temp_dir, "malicious.zip")
            with zipfile.ZipFile(zip_source, "w") as zf:
                # Try to write outside the extraction directory
                zf.writestr("../../../etc/passwd", "malicious content")

            def mock_download_impl(response, dest_path):
                import shutil

                shutil.copy(zip_source, dest_path)

            mock_download.side_effect = mock_download_impl

            # Should raise ValueError for zip slip attempt
            with pytest.raises(ValueError, match="Zip slip attack detected"):
                agent_registry.download_skill("malicious-skill", temp_dir)
