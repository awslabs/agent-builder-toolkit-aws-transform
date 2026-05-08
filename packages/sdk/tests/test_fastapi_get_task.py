# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for GetTask FastAPI endpoint
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agent_builder_sdk.fastapi_server import app


class TestGetTaskEndpoint:
    """Test cases for /tasks/get endpoint."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    @patch("agent_builder_sdk.task_handler.get_agent_context_from_env")
    def test_get_task_endpoint_feature_enabled(self, mock_get_context):
        """Test /tasks/get endpoint when feature is enabled and task ID matches job ID."""
        mock_context = MagicMock()
        mock_context.job_id = "test-job-123"
        mock_get_context.return_value = mock_context

        request_data = {"id": "test-job-123"}

        response = self.client.post("/tasks/get", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["result"] is not None
        assert data["result"]["id"] == "test-job-123"
        assert data["result"]["kind"] == "task"
        assert data["result"]["status"]["state"] == "working"
        assert isinstance(data["result"]["contextId"], str)

    @patch("agent_builder_sdk.task_handler.get_agent_context_from_env")
    def test_get_task_endpoint_task_not_found(self, mock_get_context):
        """Test /tasks/get endpoint when task ID doesn't match job ID."""
        mock_context = MagicMock()
        mock_context.job_id = "different-job-456"
        mock_get_context.return_value = mock_context

        request_data = {"id": "test-task-123"}

        response = self.client.post("/tasks/get", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["result"] is None
        assert data["error"] is not None
        assert data["error"]["message"] == "Task not found: test-task-123"
