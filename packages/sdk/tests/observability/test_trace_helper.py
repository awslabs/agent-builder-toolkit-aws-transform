"""Unit tests for trace_helper module."""

import hashlib
import os
import uuid
from unittest.mock import patch

from agent_builder_sdk.observability.trace_helper import get_trace_attributes


def test_get_trace_attributes_with_all_env_vars_present():
    """Test when all required environment variables are present."""
    with patch.dict(
        os.environ,
        {"WORKSPACE_ID": "workspace-123", "JOB_ID": "job-456", "AGENT_INSTANCE_ID": "agent-789"},
    ):
        result = get_trace_attributes()

        expected_hash = hashlib.sha256(
            "workspace-123_job-456_agent-789".encode("utf-8")
        ).hexdigest()
        assert result["session.id"] == expected_hash
        assert result["workspace.id"] == "workspace-123"
        assert result["job.id"] == "job-456"
        assert result["agent.instance.id"] == "agent-789"
        assert result["service.name"] == "atx-agent"


def test_get_trace_attributes_with_missing_workspace_id():
    """Test when WORKSPACE_ID is missing."""
    with patch.dict(
        os.environ, {"JOB_ID": "job-456", "AGENT_INSTANCE_ID": "agent-789"}, clear=True
    ):
        result = get_trace_attributes()

        # Should generate UUID when any env var is missing
        session_id = result["session.id"]
        assert len(session_id) == 36  # UUID length
        assert "-" in session_id  # UUID format
        # Verify it's a valid UUID
        uuid.UUID(session_id)


def test_get_trace_attributes_with_missing_job_id():
    """Test when JOB_ID is missing."""
    with patch.dict(
        os.environ, {"WORKSPACE_ID": "workspace-123", "AGENT_INSTANCE_ID": "agent-789"}, clear=True
    ):
        result = get_trace_attributes()

        session_id = result["session.id"]
        assert len(session_id) == 36
        uuid.UUID(session_id)


def test_get_trace_attributes_with_missing_agent_instance_id():
    """Test when AGENT_INSTANCE_ID is missing."""
    with patch.dict(os.environ, {"WORKSPACE_ID": "workspace-123", "JOB_ID": "job-456"}, clear=True):
        result = get_trace_attributes()

        session_id = result["session.id"]
        assert len(session_id) == 36
        uuid.UUID(session_id)


def test_get_trace_attributes_with_all_env_vars_missing():
    """Test when all environment variables are missing."""
    with patch.dict(os.environ, {}, clear=True):
        result = get_trace_attributes()

        session_id = result["session.id"]
        assert len(session_id) == 36
        uuid.UUID(session_id)


def test_get_trace_attributes_with_custom_service_name():
    """Test with custom service name."""
    with patch.dict(
        os.environ,
        {"WORKSPACE_ID": "workspace-123", "JOB_ID": "job-456", "AGENT_INSTANCE_ID": "agent-789"},
    ):
        result = get_trace_attributes(service_name="custom-service")

        expected_hash = hashlib.sha256(
            "workspace-123_job-456_agent-789".encode("utf-8")
        ).hexdigest()
        assert result["service.name"] == "custom-service"
        assert result["session.id"] == expected_hash


def test_get_trace_attributes_with_custom_session_id():
    """Test with custom session ID provided."""
    custom_session_id = "custom-session-123"

    result = get_trace_attributes(session_id=custom_session_id)

    assert result["session.id"] == custom_session_id
