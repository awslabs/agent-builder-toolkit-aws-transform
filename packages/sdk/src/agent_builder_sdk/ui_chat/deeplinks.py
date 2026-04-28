"""
UI Deeplinks Module

This module provides helper methods to create deeplinks that can be sent to user chat.
The Deeplink component converts custom aws-transform:// URLs into WebApp routes,
enabling consistent navigation patterns across the application.

It supports both static deeplinks with explicit IDs and dynamic deeplinks that
resolve based on current context.

Static Deeplinks (aws-transform://):
    Static deeplinks contain all required parameters in the URL and don't depend
    on current page context.

Dynamic Deeplinks (aws-transform://~/):
    Dynamic deeplinks use the ~/ prefix and resolve based on current page context
    or provided context object. They're useful for relative navigation within the
    current workspace or job.

Documentation: https://quip-amazon.com/NNz1ALRfopmI/ATX-Deeplink-Schema-Guide
Implementation: https://code.amazon.com/packages/ElasticGumbyUIComponents/blobs/heads/mainline/--/src/sharedComponents/Deeplink/routes.ts
"""

from enum import Enum


class SegmentName(Enum):
    """URL segment names used in deeplink construction."""

    TAB = "tab"
    WORKSPACES = "workspaces"
    JOBS = "jobs"
    TASKS = "tasks"
    DASHBOARD = "dashboard"
    ARTIFACTS = "artifacts"
    APPROVALS = "approvals"
    WORKLOGS = "worklogs"


class Deeplinks:
    """
    Unified deeplink generator that creates both static and dynamic URLs.

    Each method accepts optional workspace_id and job_id parameters:
    - If workspace_id is provided: creates static deeplink (aws-transform://)
    - If workspace_id is None: creates dynamic deeplink (aws-transform://~/)

    This approach consolidates all functionality into single methods that handle
    both static and dynamic contexts automatically.
    """

    @staticmethod
    def _validate_workspace_job_dependency(workspace_id: str | None, job_id: str | None) -> None:
        """
        Validate that job_id is provided when workspace_id is provided.

        Args:
            workspace_id: Optional workspace ID
            job_id: Optional job ID

        Raises:
            ValueError: If workspace_id is provided without job_id
        """
        if workspace_id and not job_id:
            raise ValueError("job_id is required when workspace_id is provided")

    @staticmethod
    def _generate_url(segments: list[str | SegmentName]) -> str:
        """
        Generate a URL path from a list of segments.

        Args:
            segments: List of URL segments (strings or SegmentName enum values)

        Returns:
            URL path string with segments joined by '/'

        Example:
            >>> Deeplinks._generate_url([SegmentName.WORKSPACES, "ws-123", SegmentName.JOBS, "job-456"])
            'workspaces/ws-123/jobs/job-456'
        """
        return "/".join(
            [segment.value if isinstance(segment, SegmentName) else segment for segment in segments]
        )

    @staticmethod
    def _format_deeplink(url_path: str, display_text: str, is_dynamic: bool = False) -> str:
        """
        Internal helper to format a deeplink URL with markdown.

        Args:
            url_path: The relative URL path
            display_text: Text to display in markdown link
            is_dynamic: If True, creates dynamic deeplinks with '~/' prefix

        Returns:
            Markdown-formatted deeplink

        Example:
            >>> Deeplinks._format_deeplink("workspaces/ws-123", "My Workspace", is_dynamic=False)
            '[My Workspace](aws-transform://workspaces/ws-123)'
            >>> Deeplinks._format_deeplink("jobs/job-456", "My Job", is_dynamic=True)
            '[My Job](aws-transform://~/jobs/job-456)'
        """
        base_url = "aws-transform://"
        if is_dynamic:
            base_url += "~/"
        full_url = f"{base_url}{url_path}"
        return f"[{display_text}]({full_url})"

    @staticmethod
    def workspace(display_text: str, workspace_id: str) -> str:
        """
        Generate a deeplink to navigate to a specific workspace.

        Args:
            display_text: Text to display in markdown link
            workspace_id: The unique identifier of the workspace

        Returns:
            Markdown-formatted deeplink to the workspace

        Example:
            >>> Deeplinks.workspace("My Workspace", workspace_id="ws-12345")
            '[My Workspace](aws-transform://workspaces/ws-12345)'
        """
        url_path = Deeplinks._generate_url([SegmentName.WORKSPACES, workspace_id])
        return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)

    @staticmethod
    def job(display_text: str, job_id: str, workspace_id: str | None = None) -> str:
        """
        Generate a deeplink to navigate to a specific job.

        Args:
            display_text: Text to display in markdown link
            job_id: The unique identifier of the job
            workspace_id: Optional workspace ID. If provided, creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the job

        Example:
            >>> Deeplinks.job("Migration Job", job_id="job-67890", workspace_id="ws-12345")
            '[Migration Job](aws-transform://workspaces/ws-12345/jobs/job-67890)'
            >>> Deeplinks.job("Migration Job", job_id="job-67890")
            '[Migration Job](aws-transform://~/jobs/job-67890)'
        """
        if workspace_id:
            url_path = Deeplinks._generate_url(
                [SegmentName.WORKSPACES, workspace_id, SegmentName.JOBS, job_id]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        else:
            url_path = Deeplinks._generate_url([SegmentName.JOBS, job_id])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def dashboard(
        display_text: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to a job's dashboard.

        Args:
            display_text: Text to display in markdown link
            job_id: Optional job ID. Required if workspace_id is provided.
                workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the dashboard

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.dashboard("Job Dashboard", job_id="job-67890", workspace_id="ws-12345")
            '[Job Dashboard](aws-transform://workspaces/ws-12345/jobs/job-67890/dashboard)'
            >>> Deeplinks.dashboard("Job Dashboard", job_id="job-67890")
            '[Job Dashboard](aws-transform://~/jobs/job-67890/dashboard)'
            >>> Deeplinks.dashboard("Dashboard")
            '[Dashboard](aws-transform://~/tab/dashboard)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.DASHBOARD,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url([SegmentName.JOBS, job_id, SegmentName.DASHBOARD])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TAB, SegmentName.DASHBOARD])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def task(
        display_text: str, task_id: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to a specific task.

        Args:
            display_text: Text to display in markdown link
            task_id: The unique identifier of the task
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the task

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.task("Network Task", task_id="task-11111", job_id="job-67890", workspace_id="ws-12345")
            '[Network Task](aws-transform://workspaces/ws-12345/jobs/job-67890/tasks/task-11111)'
            >>> Deeplinks.task("Network Task", task_id="task-11111", job_id="job-67890")
            '[Network Task](aws-transform://~/jobs/job-67890/tasks/task-11111)'
            >>> Deeplinks.task("Network Task", task_id="task-11111")
            '[Network Task](aws-transform://~/tasks/task-11111)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.TASKS,
                    task_id,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url(
                [SegmentName.JOBS, job_id, SegmentName.TASKS, task_id]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TASKS, task_id])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def tasks_tab(
        display_text: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to the tasks tab.

        Args:
            display_text: Text to display in markdown link
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the tasks tab

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.tasks_tab("View Tasks", job_id="job-67890", workspace_id="ws-12345")
            '[View Tasks](aws-transform://workspaces/ws-12345/jobs/job-67890/tab/tasks)'
            >>> Deeplinks.tasks_tab("View Tasks", job_id="job-67890")
            '[View Tasks](aws-transform://~/jobs/job-67890/tab/tasks)'
            >>> Deeplinks.tasks_tab("View Tasks")
            '[View Tasks](aws-transform://~/tab/tasks)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.TAB,
                    SegmentName.TASKS,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url(
                [SegmentName.JOBS, job_id, SegmentName.TAB, SegmentName.TASKS]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TAB, SegmentName.TASKS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def artifact(
        display_text: str,
        artifact_name: str,
        job_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        """
        Generate a deeplink to navigate to a specific artifact.

        Args:
            display_text: Text to display in markdown link
            artifact_name: The name of the artifact
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the artifact

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.artifact("View Report", artifact_name="report.json", job_id="job-67890", workspace_id="ws-12345")
            '[View Report](aws-transform://workspaces/ws-12345/jobs/job-67890/artifacts/report.json)'
            >>> Deeplinks.artifact("View Report", artifact_name="report.json", job_id="job-67890")
            '[View Report](aws-transform://~/jobs/job-67890/artifacts/report.json)'
            >>> Deeplinks.artifact("View Report", artifact_name="report.json")
            '[View Report](aws-transform://~/artifacts/report.json)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.ARTIFACTS,
                    artifact_name,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url(
                [SegmentName.JOBS, job_id, SegmentName.ARTIFACTS, artifact_name]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.ARTIFACTS, artifact_name])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def artifacts_list(
        display_text: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to the artifacts list.

        Args:
            display_text: Text to display in markdown link
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the artifacts list

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.artifacts_list("View Artifacts", job_id="job-67890", workspace_id="ws-12345")
            '[View Artifacts](aws-transform://workspaces/ws-12345/jobs/job-67890/artifacts)'
            >>> Deeplinks.artifacts_list("View Artifacts", job_id="job-67890")
            '[View Artifacts](aws-transform://~/jobs/job-67890/artifacts)'
            >>> Deeplinks.artifacts_list("View Artifacts")
            '[View Artifacts](aws-transform://~/tab/artifacts)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.ARTIFACTS,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url([SegmentName.JOBS, job_id, SegmentName.ARTIFACTS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TAB, SegmentName.ARTIFACTS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def approvals(
        display_text: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to the approvals page.

        Args:
            display_text: Text to display in markdown link
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the approvals page

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.approvals("View Approvals", job_id="job-67890", workspace_id="ws-12345")
            '[View Approvals](aws-transform://workspaces/ws-12345/jobs/job-67890/approvals)'
            >>> Deeplinks.approvals("View Approvals", job_id="job-67890")
            '[View Approvals](aws-transform://~/jobs/job-67890/approvals)'
            >>> Deeplinks.approvals("View Approvals")
            '[View Approvals](aws-transform://~/tab/approvals)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.APPROVALS,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url([SegmentName.JOBS, job_id, SegmentName.APPROVALS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TAB, SegmentName.APPROVALS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)

    @staticmethod
    def worklogs(
        display_text: str, job_id: str | None = None, workspace_id: str | None = None
    ) -> str:
        """
        Generate a deeplink to navigate to the worklogs tab.

        Args:
            display_text: Text to display in markdown link
            job_id: Optional job ID. Required if workspace_id is provided.
            workspace_id: Optional workspace ID. If provided (with job_id), creates static deeplink.
                         If None, creates dynamic deeplink using current context.

        Returns:
            Markdown-formatted deeplink to the worklogs tab

        Raises:
            ValueError: If workspace_id is provided without job_id

        Example:
            >>> Deeplinks.worklogs("View Logs", job_id="job-67890", workspace_id="ws-12345")
            '[View Logs](aws-transform://workspaces/ws-12345/jobs/job-67890/tab/worklogs)'
            >>> Deeplinks.worklogs("View Logs", job_id="job-67890")
            '[View Logs](aws-transform://~/jobs/job-67890/tab/worklogs)'
            >>> Deeplinks.worklogs("View Logs")
            '[View Logs](aws-transform://~/tab/worklogs)'
        """
        Deeplinks._validate_workspace_job_dependency(workspace_id, job_id)

        if workspace_id is not None and job_id is not None:
            url_path = Deeplinks._generate_url(
                [
                    SegmentName.WORKSPACES,
                    workspace_id,
                    SegmentName.JOBS,
                    job_id,
                    SegmentName.TAB,
                    SegmentName.WORKLOGS,
                ]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=False)
        elif job_id:
            url_path = Deeplinks._generate_url(
                [SegmentName.JOBS, job_id, SegmentName.TAB, SegmentName.WORKLOGS]
            )
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
        else:
            url_path = Deeplinks._generate_url([SegmentName.TAB, SegmentName.WORKLOGS])
            return Deeplinks._format_deeplink(url_path, display_text, is_dynamic=True)
