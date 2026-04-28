"""
Unit tests for JobManager.
"""

from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.job_manager import JobManager, JobStatus


@pytest.fixture
def mock_client():
    """Mock agentic API client."""
    return mock.Mock()


@pytest.fixture
def job_manager(mock_client):
    """Create JobManager instance for testing."""
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agentic_api_helper.retrieve_auth_token",
        return_value="test-token",
    ):
        manager = JobManager(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            client=mock_client,
        )
        yield manager


class TestJobManager:
    """Test JobManager class."""

    def test_update_job_status_success(self, job_manager, mock_client):
        """Test successful job status update."""
        mock_client.update_job_status.return_value = {"status": "success"}

        result = job_manager.update_job_status(JobStatus.EXECUTING)

        assert result == {"status": "success"}
        mock_client.update_job_status.assert_called_once()
        call_args = mock_client.update_job_status.call_args[1]
        assert call_args["status"] == "EXECUTING"

    def test_update_job_status_with_info(self, job_manager, mock_client):
        """Test job status update with status info."""
        mock_client.update_job_status.return_value = {"status": "success"}
        status_info = {"message": "Test message"}

        result = job_manager.update_job_status(JobStatus.FAILED, status_info)

        assert result == {"status": "success"}
        call_args = mock_client.update_job_status.call_args[1]
        assert call_args["status"] == "FAILED"
        assert call_args["statusInfo"] == status_info

    def test_update_job_status_error(self, job_manager, mock_client):
        """Test job status update error handling."""
        mock_client.update_job_status.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            job_manager.update_job_status(JobStatus.EXECUTING)

    def test_get_job_status_success(self, job_manager, mock_client):
        """Test successful job status retrieval."""
        mock_client.get_job.return_value = {"job": {"statusDetails": {"status": "EXECUTING"}}}

        status = job_manager.get_job_status()

        assert status == "EXECUTING"
        mock_client.get_job.assert_called_once()
        call_args = mock_client.get_job.call_args[1]
        assert call_args["includeObjective"] is False

    def test_get_job_status_error(self, job_manager, mock_client):
        """Test job status retrieval error handling."""
        mock_client.get_job.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            job_manager.get_job_status()

    def test_transition_to_executing_when_assessing(self, job_manager, mock_client):
        """Test transition from ASSESSING to EXECUTING."""
        mock_client.get_job.return_value = {"job": {"statusDetails": {"status": "ASSESSING"}}}
        mock_client.update_job_status.return_value = {"status": "success"}

        job_manager.transition_to_executing_if_assessing()

        mock_client.get_job.assert_called_once()
        mock_client.update_job_status.assert_called_once()
        call_args = mock_client.update_job_status.call_args[1]
        assert call_args["status"] == "EXECUTING"

    def test_transition_to_executing_when_not_assessing(self, job_manager, mock_client):
        """Test no transition when not in ASSESSING status."""
        mock_client.get_job.return_value = {"job": {"statusDetails": {"status": "EXECUTING"}}}

        job_manager.transition_to_executing_if_assessing()

        mock_client.get_job.assert_called_once()
        mock_client.update_job_status.assert_not_called()

    def test_transition_to_executing_handles_get_error(self, job_manager, mock_client):
        """Test transition handles get_job_status error."""
        mock_client.get_job.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            job_manager.transition_to_executing_if_assessing()

        mock_client.update_job_status.assert_not_called()
