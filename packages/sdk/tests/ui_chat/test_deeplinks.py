"""Tests for UI Deeplinks module."""

import pytest

from agent_builder_sdk.ui_chat.deeplinks import Deeplinks


class TestWorkspace:
    """Tests for workspace deeplink generation."""

    def test_workspace_static(self):
        """Test static workspace deeplink."""
        result = Deeplinks.workspace("My Workspace", workspace_id="ws-12345")
        assert result == "[My Workspace](aws-transform://workspaces/ws-12345)"


class TestJob:
    """Tests for job deeplink generation."""

    def test_job_static(self):
        """Test static job deeplink with workspace_id."""
        result = Deeplinks.job("Migration Job", job_id="job-67890", workspace_id="ws-12345")
        assert result == "[Migration Job](aws-transform://workspaces/ws-12345/jobs/job-67890)"

    def test_job_dynamic(self):
        """Test dynamic job deeplink without workspace_id."""
        result = Deeplinks.job("Migration Job", job_id="job-67890")
        assert result == "[Migration Job](aws-transform://~/jobs/job-67890)"


class TestDashboard:
    """Tests for dashboard deeplink generation."""

    def test_dashboard_static(self):
        """Test static dashboard deeplink with workspace_id and job_id."""
        result = Deeplinks.dashboard("Job Dashboard", job_id="job-67890", workspace_id="ws-12345")
        assert (
            result
            == "[Job Dashboard](aws-transform://workspaces/ws-12345/jobs/job-67890/dashboard)"
        )

    def test_dashboard_dynamic_with_job(self):
        """Test dynamic dashboard deeplink with job_id only."""
        result = Deeplinks.dashboard("Job Dashboard", job_id="job-67890")
        assert result == "[Job Dashboard](aws-transform://~/jobs/job-67890/dashboard)"

    def test_dashboard_dynamic_no_context(self):
        """Test dynamic dashboard deeplink without any context."""
        result = Deeplinks.dashboard("Dashboard")
        assert result == "[Dashboard](aws-transform://~/tab/dashboard)"

    def test_dashboard_raises_error_workspace_without_job(self):
        """Test that dashboard raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.dashboard("Dashboard", workspace_id="ws-12345")


class TestTask:
    """Tests for task deeplink generation."""

    def test_task_static(self):
        """Test static task deeplink with workspace_id and job_id."""
        result = Deeplinks.task(
            "Network Task", task_id="task-11111", job_id="job-67890", workspace_id="ws-12345"
        )
        assert (
            result
            == "[Network Task](aws-transform://workspaces/ws-12345/jobs/job-67890/tasks/task-11111)"
        )

    def test_task_dynamic_with_job(self):
        """Test dynamic task deeplink with job_id only."""
        result = Deeplinks.task("Network Task", task_id="task-11111", job_id="job-67890")
        assert result == "[Network Task](aws-transform://~/jobs/job-67890/tasks/task-11111)"

    def test_task_dynamic_no_context(self):
        """Test dynamic task deeplink without any context."""
        result = Deeplinks.task("Network Task", task_id="task-11111")
        assert result == "[Network Task](aws-transform://~/tasks/task-11111)"

    def test_task_raises_error_workspace_without_job(self):
        """Test that task raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.task("Task", task_id="task-11111", workspace_id="ws-12345")


class TestTasksTab:
    """Tests for tasks tab deeplink generation."""

    def test_tasks_tab_static(self):
        """Test static tasks tab deeplink with workspace_id and job_id."""
        result = Deeplinks.tasks_tab("View Tasks", job_id="job-67890", workspace_id="ws-12345")
        assert (
            result == "[View Tasks](aws-transform://workspaces/ws-12345/jobs/job-67890/tab/tasks)"
        )

    def test_tasks_tab_dynamic_with_job(self):
        """Test dynamic tasks tab deeplink with job_id only."""
        result = Deeplinks.tasks_tab("View Tasks", job_id="job-67890")
        assert result == "[View Tasks](aws-transform://~/jobs/job-67890/tab/tasks)"

    def test_tasks_tab_dynamic_no_context(self):
        """Test dynamic tasks tab deeplink without any context."""
        result = Deeplinks.tasks_tab("View Tasks")
        assert result == "[View Tasks](aws-transform://~/tab/tasks)"

    def test_tasks_tab_raises_error_workspace_without_job(self):
        """Test that tasks_tab raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.tasks_tab("Tasks", workspace_id="ws-12345")


class TestArtifact:
    """Tests for artifact deeplink generation."""

    def test_artifact_static(self):
        """Test static artifact deeplink with workspace_id and job_id."""
        result = Deeplinks.artifact(
            "View Report", artifact_name="report.json", job_id="job-67890", workspace_id="ws-12345"
        )
        assert (
            result
            == "[View Report](aws-transform://workspaces/ws-12345/jobs/job-67890/artifacts/report.json)"
        )

    def test_artifact_dynamic_with_job(self):
        """Test dynamic artifact deeplink with job_id only."""
        result = Deeplinks.artifact("View Report", artifact_name="report.json", job_id="job-67890")
        assert result == "[View Report](aws-transform://~/jobs/job-67890/artifacts/report.json)"

    def test_artifact_dynamic_no_context(self):
        """Test dynamic artifact deeplink without any context."""
        result = Deeplinks.artifact("View Report", artifact_name="report.json")
        assert result == "[View Report](aws-transform://~/artifacts/report.json)"

    def test_artifact_raises_error_workspace_without_job(self):
        """Test that artifact raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.artifact("Report", artifact_name="report.json", workspace_id="ws-12345")


class TestArtifactsList:
    """Tests for artifacts list deeplink generation."""

    def test_artifacts_list_static(self):
        """Test static artifacts list deeplink with workspace_id and job_id."""
        result = Deeplinks.artifacts_list(
            "View Artifacts", job_id="job-67890", workspace_id="ws-12345"
        )
        assert (
            result
            == "[View Artifacts](aws-transform://workspaces/ws-12345/jobs/job-67890/artifacts)"
        )

    def test_artifacts_list_dynamic_with_job(self):
        """Test dynamic artifacts list deeplink with job_id only."""
        result = Deeplinks.artifacts_list("View Artifacts", job_id="job-67890")
        assert result == "[View Artifacts](aws-transform://~/jobs/job-67890/artifacts)"

    def test_artifacts_list_dynamic_no_context(self):
        """Test dynamic artifacts list deeplink without any context."""
        result = Deeplinks.artifacts_list("View Artifacts")
        assert result == "[View Artifacts](aws-transform://~/tab/artifacts)"

    def test_artifacts_list_raises_error_workspace_without_job(self):
        """Test that artifacts_list raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.artifacts_list("Artifacts", workspace_id="ws-12345")


class TestApprovals:
    """Tests for approvals deeplink generation."""

    def test_approvals_static(self):
        """Test static approvals deeplink with workspace_id and job_id."""
        result = Deeplinks.approvals("View Approvals", job_id="job-67890", workspace_id="ws-12345")
        assert (
            result
            == "[View Approvals](aws-transform://workspaces/ws-12345/jobs/job-67890/approvals)"
        )

    def test_approvals_dynamic_with_job(self):
        """Test dynamic approvals deeplink with job_id only."""
        result = Deeplinks.approvals("View Approvals", job_id="job-67890")
        assert result == "[View Approvals](aws-transform://~/jobs/job-67890/approvals)"

    def test_approvals_dynamic_no_context(self):
        """Test dynamic approvals deeplink without any context."""
        result = Deeplinks.approvals("View Approvals")
        assert result == "[View Approvals](aws-transform://~/tab/approvals)"

    def test_approvals_raises_error_workspace_without_job(self):
        """Test that approvals raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.approvals("Approvals", workspace_id="ws-12345")


class TestWorklogs:
    """Tests for worklogs deeplink generation."""

    def test_worklogs_static(self):
        """Test static worklogs deeplink with workspace_id and job_id."""
        result = Deeplinks.worklogs("View Logs", job_id="job-67890", workspace_id="ws-12345")
        assert (
            result == "[View Logs](aws-transform://workspaces/ws-12345/jobs/job-67890/tab/worklogs)"
        )

    def test_worklogs_dynamic_with_job(self):
        """Test dynamic worklogs deeplink with job_id only."""
        result = Deeplinks.worklogs("View Logs", job_id="job-67890")
        assert result == "[View Logs](aws-transform://~/jobs/job-67890/tab/worklogs)"

    def test_worklogs_dynamic_no_context(self):
        """Test dynamic worklogs deeplink without any context."""
        result = Deeplinks.worklogs("View Logs")
        assert result == "[View Logs](aws-transform://~/tab/worklogs)"

    def test_worklogs_raises_error_workspace_without_job(self):
        """Test that worklogs raises error when workspace_id provided without job_id."""
        with pytest.raises(ValueError, match="job_id is required when workspace_id is provided"):
            Deeplinks.worklogs("Logs", workspace_id="ws-12345")
