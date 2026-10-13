# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for HeartbeatService."""

import asyncio
import threading
import time
from unittest.mock import Mock, patch

import pytest

from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.heartbeat.heartbeat_service import HeartbeatService
from agent_builder_sdk.server.server_models import AgentRuntimeContext


async def _wait_until(predicate, timeout=5.0):
    """Poll predicate without blocking the event loop (the loop work runs in threads)."""

    async def poll():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


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

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_instance_manager_with_context")
    def test_returns_false_when_agent_id_unknown(self, mock_get_manager, context_no_agent_id):
        mock_get_manager.return_value.get_status.return_value = {"agentInstanceStatus": "RUNNING"}
        service = HeartbeatService(context_no_agent_id)
        assert service._should_enable() is False

    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agentic_api_client")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_registry")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_instance_manager_with_context")
    def test_reads_agent_id_from_instance_when_missing(
        self, mock_get_manager, mock_get_registry, mock_get_client, context_no_agent_id
    ):
        mock_get_manager.return_value.get_status.return_value = {
            "agentId": "my-agent",
            "agentVersion": "2.0",
        }
        mock_registry = Mock()
        mock_registry._inject_request_context.side_effect = lambda d: {**d, "requestContext": {}}
        mock_registry.client.get_agent_version.return_value = {
            "configuration": {"monitoringType": MonitoringType.HEARTBEAT.value}
        }
        mock_get_registry.return_value = mock_registry

        service = HeartbeatService(context_no_agent_id)
        assert service._should_enable() is True
        mock_get_manager.return_value.get_status.assert_called_once_with("agent-789")
        mock_registry.client.get_agent_version.assert_called_once_with(
            name="my-agent", version="2.0", requestContext={}
        )

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
    def test_returns_none_on_exception(self, mock_get_registry, mock_get_client, context):
        mock_get_registry.side_effect = Exception("connection error")

        service = HeartbeatService(context)
        assert service._should_enable() is None


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

    @pytest.mark.asyncio
    async def test_stop_mid_beat_skips_running_write(self, context):
        """A beat still reading the status when stop() is called must not write RUNNING."""
        service = HeartbeatService(context, interval_minutes=0)
        reading, release, beat_done = threading.Event(), threading.Event(), threading.Event()
        real_send = service._send_heartbeat

        def slow_status(*_):
            reading.set()
            release.wait(5)
            return "RUNNING"

        def tracked_send():
            try:
                real_send()
            finally:
                beat_done.set()

        with patch.object(service, "_should_enable", return_value=True), patch.object(
            service, "_send_heartbeat", side_effect=tracked_send
        ), patch(
            "agent_builder_sdk.heartbeat.heartbeat_service.get_agent_status",
            side_effect=slow_status,
        ), patch(
            "agent_builder_sdk.heartbeat.heartbeat_service.set_agent_running"
        ) as mock_set_running:
            await service.start()
            await _wait_until(reading.is_set)
            await service.stop()
            release.set()
            await _wait_until(beat_done.is_set)

        mock_set_running.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_waits_for_running_write_in_flight(self, context):
        """stop() returns only after a RUNNING write already on the wire has finished."""
        service = HeartbeatService(context, interval_minutes=0)
        writing, release = threading.Event(), threading.Event()

        def slow_write(*_):
            writing.set()
            release.wait(5)

        with patch.object(service, "_should_enable", return_value=True), patch(
            "agent_builder_sdk.heartbeat.heartbeat_service.get_agent_status",
            return_value="RUNNING",
        ), patch(
            "agent_builder_sdk.heartbeat.heartbeat_service.set_agent_running",
            side_effect=slow_write,
        ):
            await service.start()
            await _wait_until(writing.is_set)
            stopping = asyncio.create_task(service.stop())
            await asyncio.sleep(0.1)
            assert not stopping.done()  # still waiting for the write
            release.set()
            await asyncio.wait_for(stopping, timeout=5)


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

    @pytest.mark.parametrize("status", ["INVOKING", "INVOKED", "STOPPING", "UNRESPONSIVE"])
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.set_agent_running")
    @patch("agent_builder_sdk.heartbeat.heartbeat_service.get_agent_status")
    def test_skips_when_not_running(self, mock_get_status, mock_set_running, status, context):
        mock_get_status.return_value = status
        HeartbeatService(context)._send_heartbeat()
        mock_set_running.assert_not_called()


class TestHeartbeatLoop:
    """Test the background heartbeat loop."""

    @pytest.mark.asyncio
    async def test_loop_survives_send_failure(self, context):
        service = HeartbeatService(context, interval_minutes=0)  # 0 for fast test

        call_count = 0

        def flaky_send():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error")

        with patch.object(service, "_should_enable", return_value=True), patch.object(
            service, "_send_heartbeat", side_effect=flaky_send
        ):
            await service.start()
            await _wait_until(lambda: call_count >= 2)
            await service.stop()

        assert call_count >= 2  # the loop kept beating after the first send raised

    @pytest.mark.asyncio
    async def test_unknown_type_is_rechecked_until_heartbeat(self, context):
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(
            service, "_should_enable", side_effect=[None, None, True]
        ) as mock_enable, patch.object(service, "_send_heartbeat") as mock_send:
            await service.start()
            await _wait_until(lambda: mock_send.called)
            await service.stop()

        assert mock_enable.call_count == 3

    @pytest.mark.asyncio
    async def test_loop_exits_when_type_resolves_to_not_heartbeat(self, context):
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(service, "_should_enable", side_effect=[None, None, False]), patch.object(
            service, "_send_heartbeat"
        ) as mock_send:
            await service.start()
            await asyncio.wait_for(service._task, timeout=5)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_calls_do_not_block_event_loop(self, context):
        """start()'s lookup, the loop's re-check and the send all run in worker threads."""
        service = HeartbeatService(context, interval_minutes=0)
        lookups = iter([None, True])  # unknown at start, HEARTBEAT on the first re-check
        sent = threading.Event()

        def slow_lookup():
            time.sleep(0.3)
            return next(lookups)

        def slow_send():
            time.sleep(0.3)
            sent.set()

        gaps = []

        async def ticker():  # a concurrent coroutine; a call on the loop thread stalls it
            while not sent.is_set():
                started = time.monotonic()
                await asyncio.sleep(0.01)
                gaps.append(time.monotonic() - started)

        with patch.object(service, "_should_enable", side_effect=slow_lookup), patch.object(
            service, "_send_heartbeat", side_effect=slow_send
        ):
            ticking = asyncio.create_task(ticker())
            await asyncio.sleep(0)  # let the ticker start before start() does its lookup
            await service.start()
            await asyncio.wait_for(ticking, timeout=5)  # ends after the first send
            await service.stop()

        assert max(gaps) < 0.2  # each call takes 0.3s
