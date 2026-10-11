# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for HeartbeatService."""

import asyncio
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.heartbeat.heartbeat_service import HeartbeatService
from agent_builder_sdk.server.server_models import AgentRuntimeContext


@pytest.fixture
def context():
    return AgentRuntimeContext(
        workspace_id="ws-123",
        job_id="job-456",
        agent_instance_id="agent-789",
        agent_id="my-agent",
        agent_version="1.0",
    )


@pytest.fixture
def context_no_agent_id():
    return AgentRuntimeContext(
        workspace_id="ws-123",
        job_id="job-456",
        agent_instance_id="agent-789",
    )


class TestShouldEnable:
    """Test HeartbeatService._should_enable."""

    def test_returns_false_when_no_agent_id(self, context_no_agent_id):
        service = HeartbeatService(context_no_agent_id)
        assert service._should_enable() is False

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agentic_api_client")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_registry")
    def test_returns_true_for_heartbeat_type(self, mock_get_registry, mock_get_client, context):
        mock_registry = Mock()
        mock_registry._inject_request_context.side_effect = lambda d: {**d, "requestContext": {}}
        mock_registry.client.get_agent_version.return_value = {
            "configuration": {"monitoringType": MonitoringType.HEARTBEAT.value}
        }
        mock_get_registry.return_value = mock_registry

        service = HeartbeatService(context)
        assert service._should_enable() is True
        mock_registry.client.get_agent_version.assert_called_once()

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agentic_api_client")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_registry")
    def test_returns_false_for_healthcheck_type(self, mock_get_registry, mock_get_client, context):
        mock_registry = Mock()
        mock_registry._inject_request_context.side_effect = lambda d: {**d, "requestContext": {}}
        mock_registry.client.get_agent_version.return_value = {
            "configuration": {"monitoringType": MonitoringType.HEALTHCHECK.value}
        }
        mock_get_registry.return_value = mock_registry

        service = HeartbeatService(context)
        assert service._should_enable() is False

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agentic_api_client")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_registry")
    def test_returns_false_on_exception(self, mock_get_registry, mock_get_client, context):
        mock_get_registry.side_effect = Exception("connection error")

        service = HeartbeatService(context)
        assert service._should_enable() is False


class TestStart:
    """Test HeartbeatService.start."""

    @pytest.mark.asyncio
    async def test_starts_task_when_enabled(self, context):
        service = HeartbeatService(context)
        with patch.object(service, "_should_enable", return_value=True):
            await service.start()

        assert service._task is not None
        assert not service._task.done()

        await service.stop()

    @pytest.mark.asyncio
    async def test_no_task_when_disabled(self, context):
        service = HeartbeatService(context)
        with patch.object(service, "_should_enable", return_value=False):
            await service.start()

        assert service._task is None


class TestStop:
    """Test HeartbeatService.stop."""

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, context):
        service = HeartbeatService(context)
        with patch.object(service, "_should_enable", return_value=True):
            await service.start()

        assert service._task is not None
        await service.stop()
        assert service._task.done()

    @pytest.mark.asyncio
    async def test_stop_noop_when_no_task(self, context):
        service = HeartbeatService(context)
        await service.stop()  # should not raise


class TestSendHeartbeat:
    """Test HeartbeatService._send_heartbeat."""

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.set_agent_running")
    @patch(
        "agent_builder_sdk.heartbeat.heartbeat_service.get_agent_status",
        return_value="RUNNING",
    )
    def test_calls_set_agent_running(self, mock_get_status, mock_set_running, context):
        service = HeartbeatService(context)
        service._send_heartbeat()
        mock_set_running.assert_called_once_with("ws-123", "job-456", "agent-789")

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.set_agent_running")
    @patch(
        "agent_builder_sdk.heartbeat.heartbeat_service.get_agent_status",
        return_value="RUNNING",
    )
    def test_propagates_exception(self, mock_get_status, mock_set_running, context):
        mock_set_running.side_effect = Exception("API error")
        service = HeartbeatService(context)

        with pytest.raises(Exception, match="API error"):
            service._send_heartbeat()


class TestHeartbeatLoop:
    """Test the background heartbeat loop."""

    @pytest.mark.asyncio
    async def test_loop_calls_send_heartbeat(self, context):
        service = HeartbeatService(context, interval_minutes=0)  # 0 for fast test

        call_count = 0

        def mock_send():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                service._task.cancel()

        with patch.object(service, "_should_enable", return_value=True), patch.object(
            service, "_send_heartbeat", side_effect=mock_send
        ):
            await service.start()
            try:
                await service._task
            except asyncio.CancelledError:
                pass

        assert call_count >= 2
