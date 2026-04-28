from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_builder_sdk.custom_types.notification_types import HitlTaskStatus
from agent_builder_sdk.orchestrator_strands.tools.approval import (
    ApprovableTools,
    _upload_hitl_json_artifact,
    requires_approval,
)


@pytest.fixture
def mock_artifact_store():
    store = MagicMock()
    store.upload_artifact.return_value = "artifact-123"
    return store


@pytest.fixture
def mock_hitl_client():
    client = AsyncMock()
    client.create_hitl_task.return_value = {"hitlTaskId": "hitl-123"}
    return client


@pytest.fixture
def mock_hitl_notifier():
    return AsyncMock()


@pytest.fixture
def approvable_tools(mock_artifact_store, mock_hitl_client, mock_hitl_notifier):
    return ApprovableTools(mock_artifact_store, mock_hitl_client, mock_hitl_notifier)


@pytest.fixture
def properties_callback():
    return MagicMock(return_value={"key": "value"})


class TestApprovableTools:
    def test_init(self, mock_artifact_store, mock_hitl_client, mock_hitl_notifier):
        tools = ApprovableTools(mock_artifact_store, mock_hitl_client, mock_hitl_notifier)
        assert tools._artifact_store is mock_artifact_store
        assert tools._hitl_client is mock_hitl_client
        assert tools._hitl_notifier is mock_hitl_notifier


class TestRequiresApproval:
    @pytest.mark.asyncio
    async def test_successful_approval(self, approvable_tools, properties_callback):
        with patch(
            "agent_builder_sdk.orchestrator_strands.tools.approval._upload_hitl_json_artifact",
            return_value="artifact-456",
        ):

            @requires_approval(
                "test_action", "Test description", "component-1", properties_callback
            )
            async def test_tool(self, arg1):
                return f"result: {arg1}"

            result = await test_tool(approvable_tools, "test_value")

            assert result == "result: test_value"
            approvable_tools._hitl_client.create_hitl_task.assert_called_once()
            approvable_tools._hitl_client.start_hitl_task.assert_called_once_with("hitl-123")
            approvable_tools._hitl_notifier.wait.assert_called_once_with(
                "hitl-123", HitlTaskStatus.SUBMITTED
            )

    @pytest.mark.asyncio
    async def test_approval_with_exception(self, approvable_tools, properties_callback):
        approvable_tools._hitl_client.create_hitl_task.side_effect = Exception("Failed")

        with patch(
            "agent_builder_sdk.orchestrator_strands.tools.approval._upload_hitl_json_artifact"
        ):

            @requires_approval(
                "test_action", "Test description", "component-1", properties_callback
            )
            async def test_tool(self, arg1):
                return "result"

            with pytest.raises(Exception, match="Failed"):
                await test_tool(approvable_tools, "test_value")


class TestUploadHitlJsonArtifact:
    def test_successful_upload(self, mock_artifact_store):
        properties = {"key": "value"}

        result = _upload_hitl_json_artifact(mock_artifact_store, properties)

        assert result == "artifact-123"
        mock_artifact_store.upload_artifact.assert_called_once()

    def test_upload_with_step_id(self, mock_artifact_store):
        properties = {"key": "value"}

        result = _upload_hitl_json_artifact(mock_artifact_store, properties, "step-1")

        assert result == "artifact-123"
        call_args = mock_artifact_store.upload_artifact.call_args
        assert call_args[1]["plan_step_id"] == "step-1"
