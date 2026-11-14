# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for HeartbeatService."""

import asyncio
import logging
import threading
import time
from typing import Callable, Dict, Iterator, List, Optional
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.heartbeat.heartbeat_service import HeartbeatService
from agent_builder_sdk.server.server_models import AgentRuntimeContext

MODULE = "agent_builder_sdk.heartbeat.heartbeat_service"
PERMANENT_CODES = ["AccessDeniedException", "ResourceNotFoundException", "ValidationException"]


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "rejected"}}, "Operation")


def _logged(caplog: pytest.LogCaptureFixture) -> List[logging.LogRecord]:
    """The records the heartbeat module itself logged."""
    return [record for record in caplog.records if record.name == MODULE]


async def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Poll predicate without blocking the event loop (the loop work runs in threads)."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


@pytest.fixture
def context() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        workspace_id="ws-123",
        job_id="job-456",
        agent_instance_id="agent-789",
        agent_id="my-agent",
        agent_version="1.0",
    )


@pytest.fixture
def context_no_agent_id() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        workspace_id="ws-123",
        job_id="job-456",
        agent_instance_id="agent-789",
    )


@pytest.fixture
def registry() -> Iterator[Mock]:
    """The AgentRegistry the service reads the monitoring type from (HEARTBEAT by default)."""
    with patch(f"{MODULE}.get_agentic_api_client"), patch(
        f"{MODULE}.get_agent_registry"
    ) as get_registry:
        get_registry.return_value.get_agent_configuration.return_value = {
            "monitoringType": MonitoringType.HEARTBEAT.value
        }
        yield get_registry.return_value


@pytest.fixture
def instance_manager() -> Iterator[Mock]:
    """The AgentInstanceManager the service reads the instance's agent id and version from."""
    with patch(f"{MODULE}.get_agent_instance_manager_with_context") as get_manager:
        yield get_manager.return_value


class TestShouldEnable:
    """Test HeartbeatService._should_enable."""

    def test_returns_false_when_agent_id_unknown(
        self, instance_manager: Mock, context_no_agent_id: AgentRuntimeContext
    ) -> None:
        instance_manager.get_status.return_value = {"agentInstanceStatus": "RUNNING"}
        assert HeartbeatService(context_no_agent_id)._should_enable() is False

    def test_reads_agent_id_from_instance_when_missing(
        self, instance_manager: Mock, registry: Mock, context_no_agent_id: AgentRuntimeContext
    ) -> None:
        instance_manager.get_status.return_value = {"agentId": "my-agent", "agentVersion": "2.0"}

        assert HeartbeatService(context_no_agent_id)._should_enable() is True
        instance_manager.get_status.assert_called_once_with("agent-789")
        registry.get_agent_configuration.assert_called_once_with("my-agent", "2.0")

    def test_reads_version_from_instance_when_missing(
        self, instance_manager: Mock, registry: Mock, context: AgentRuntimeContext
    ) -> None:
        """Without a version the registry would answer for the latest one, not the running one."""
        context.agent_version = None
        instance_manager.get_status.return_value = {"agentId": "my-agent", "agentVersion": "2.0"}

        assert HeartbeatService(context)._should_enable() is True
        registry.get_agent_configuration.assert_called_once_with("my-agent", "2.0")

    def test_returns_true_for_heartbeat_type(
        self, instance_manager: Mock, registry: Mock, context: AgentRuntimeContext
    ) -> None:
        assert HeartbeatService(context)._should_enable() is True
        registry.get_agent_configuration.assert_called_once_with("my-agent", "1.0")
        instance_manager.get_status.assert_not_called()

    def test_returns_false_for_healthcheck_type(
        self, registry: Mock, context: AgentRuntimeContext
    ) -> None:
        registry.get_agent_configuration.return_value = {
            "monitoringType": MonitoringType.HEALTHCHECK.value
        }
        assert HeartbeatService(context)._should_enable() is False

    @pytest.mark.parametrize(
        "error", [Exception("connection error"), _client_error("ThrottlingException")]
    )
    def test_returns_none_on_transient_error(
        self, error: Exception, registry: Mock, context: AgentRuntimeContext
    ) -> None:
        registry.get_agent_configuration.side_effect = error
        assert HeartbeatService(context)._should_enable() is None

    @pytest.mark.parametrize("code", PERMANENT_CODES)
    def test_returns_false_with_one_warning_on_permanent_error(
        self,
        code: str,
        registry: Mock,
        context: AgentRuntimeContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        registry.get_agent_configuration.side_effect = _client_error(code)

        with caplog.at_level(logging.INFO, logger=MODULE):
            assert HeartbeatService(context)._should_enable() is False

        assert [record.levelno for record in _logged(caplog)] == [logging.WARNING]
        assert code in caplog.text

    def test_returns_false_when_instance_is_terminal(
        self,
        instance_manager: Mock,
        context_no_agent_id: AgentRuntimeContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        instance_manager.get_status.side_effect = _client_error("TerminalResourceException")

        with caplog.at_level(logging.INFO, logger=MODULE):
            assert HeartbeatService(context_no_agent_id)._should_enable() is False

        assert [record.levelno for record in _logged(caplog)] == [logging.INFO]


class TestStart:
    """Test HeartbeatService.start."""

    @pytest.mark.asyncio
    async def test_start_does_not_wait_for_the_lookup(self, context: AgentRuntimeContext) -> None:
        """Agent setup awaits start(); a slow registry must not delay it."""
        service = HeartbeatService(context, interval_minutes=0)
        looking_up, release = threading.Event(), threading.Event()

        def slow_lookup() -> bool:
            looking_up.set()
            release.wait(5)
            return True

        with patch.object(service, "_should_enable", side_effect=slow_lookup), patch.object(
            service, "_send_heartbeat", return_value=True
        ) as mock_send:
            try:
                await asyncio.wait_for(service.start(), timeout=1)
                await _wait_until(looking_up.is_set)
                mock_send.assert_not_called()
            finally:
                release.set()
            await _wait_until(lambda: mock_send.called)
            await service.stop()

    @pytest.mark.asyncio
    async def test_no_beat_when_disabled(self, context: AgentRuntimeContext) -> None:
        service = HeartbeatService(context, interval_minutes=0)
        with patch.object(service, "_should_enable", return_value=False), patch.object(
            service, "_send_heartbeat"
        ) as mock_send:
            await service.start()
            assert service._task is not None
            await asyncio.wait_for(service._task, timeout=5)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_start_adds_no_task(self, context: AgentRuntimeContext) -> None:
        """stop() cancels one task, so a second start() must not leave another loop running."""
        service = HeartbeatService(context)
        with patch.object(service, "_should_enable", return_value=True):
            await service.start()
            first = service._task
            await service.start()
            await service.stop()

        assert first is not None and first.done()

    @pytest.mark.asyncio
    async def test_healthy_run_logs(
        self,
        registry: Mock,
        context: AgentRuntimeContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Operators and the end-to-end check look for these exact lines in the agent log."""
        real_sleep = asyncio.sleep

        async def skip_interval(delay: float) -> None:
            await real_sleep(0 if delay == 300 else delay)

        service = HeartbeatService(context)
        with patch(f"{MODULE}.asyncio.sleep", new=skip_interval), patch(
            f"{MODULE}.get_agent_status", return_value="RUNNING"
        ), patch(f"{MODULE}.set_agent_running") as mock_set_running, caplog.at_level(
            logging.INFO, logger=MODULE
        ):
            await service.start()
            await _wait_until(lambda: mock_set_running.called)
            await service.stop()

        assert "Heartbeat monitoring enabled for agent my-agent" in caplog.messages
        assert "Heartbeat service started (interval: 300s)" in caplog.messages
        assert "Heartbeat sent successfully" in caplog.messages
        assert "Heartbeat disabled" not in caplog.text
        assert "Heartbeat failed" not in caplog.text


class TestStop:
    """Test HeartbeatService.stop."""

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, context: AgentRuntimeContext) -> None:
        service = HeartbeatService(context)
        with patch.object(service, "_should_enable", return_value=True):
            await service.start()

        assert service._task is not None
        await service.stop()
        assert service._task.done()

    @pytest.mark.asyncio
    async def test_stop_noop_when_no_task(self, context: AgentRuntimeContext) -> None:
        service = HeartbeatService(context)
        await service.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_mid_lookup_logs_no_start(
        self, registry: Mock, context: AgentRuntimeContext, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A lookup still in its worker thread when stop() is called must not report a start."""
        service = HeartbeatService(context)
        looking_up, release, lookup_done = threading.Event(), threading.Event(), threading.Event()
        real_lookup = service._should_enable

        def slow_configuration(*_: str) -> Dict[str, str]:
            looking_up.set()
            release.wait(5)
            return {"monitoringType": MonitoringType.HEARTBEAT.value}

        def tracked_lookup() -> Optional[bool]:
            try:
                return real_lookup()
            finally:
                lookup_done.set()

        registry.get_agent_configuration.side_effect = slow_configuration
        with patch.object(
            service, "_should_enable", side_effect=tracked_lookup
        ), caplog.at_level(logging.INFO, logger=MODULE):
            await service.start()
            await _wait_until(looking_up.is_set)
            await service.stop()
            release.set()
            await _wait_until(lookup_done.is_set)

        assert [record.getMessage() for record in _logged(caplog)] == ["Heartbeat service stopped"]

    @pytest.mark.asyncio
    async def test_stop_mid_beat_skips_running_write(self, context: AgentRuntimeContext) -> None:
        """A beat still reading the status when stop() is called must not write RUNNING."""
        service = HeartbeatService(context, interval_minutes=0)
        reading, release, beat_done = threading.Event(), threading.Event(), threading.Event()
        real_send = service._send_heartbeat

        def slow_status(*_: str) -> str:
            reading.set()
            release.wait(5)
            return "RUNNING"

        def tracked_send() -> bool:
            try:
                return real_send()
            finally:
                beat_done.set()

        with patch.object(service, "_should_enable", return_value=True), patch.object(
            service, "_send_heartbeat", side_effect=tracked_send
        ), patch(f"{MODULE}.get_agent_status", side_effect=slow_status), patch(
            f"{MODULE}.set_agent_running"
        ) as mock_set_running:
            await service.start()
            await _wait_until(reading.is_set)
            await service.stop()
            release.set()
            await _wait_until(beat_done.is_set)

        mock_set_running.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_waits_for_running_write_in_flight(
        self, context: AgentRuntimeContext
    ) -> None:
        """stop() returns only after a RUNNING write already on the wire has finished."""
        service = HeartbeatService(context, interval_minutes=0)
        writing, release = threading.Event(), threading.Event()

        def slow_write(*_: str) -> None:
            writing.set()
            release.wait(5)

        with patch.object(service, "_should_enable", return_value=True), patch(
            f"{MODULE}.get_agent_status", return_value="RUNNING"
        ), patch(f"{MODULE}.set_agent_running", side_effect=slow_write):
            await service.start()
            await _wait_until(writing.is_set)
            stopping = asyncio.create_task(service.stop())
            await asyncio.sleep(0.1)
            assert not stopping.done()  # still waiting for the write
            release.set()
            await asyncio.wait_for(stopping, timeout=5)

    @pytest.mark.asyncio
    async def test_stop_gives_up_on_a_hung_write(
        self, context: AgentRuntimeContext, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A write that outlasts STOP_TIMEOUT_SECONDS must not stall shutdown; stop() warns."""
        service = HeartbeatService(context, interval_minutes=0)
        writing, release = threading.Event(), threading.Event()

        def hung_write(*_: str) -> None:
            writing.set()
            release.wait(5)

        with patch.object(service, "_should_enable", return_value=True), patch(
            f"{MODULE}.get_agent_status", return_value="RUNNING"
        ), patch(f"{MODULE}.set_agent_running", side_effect=hung_write), patch(
            f"{MODULE}.STOP_TIMEOUT_SECONDS", 0.05
        ):
            await service.start()
            await _wait_until(writing.is_set)
            try:
                with caplog.at_level(logging.WARNING, logger=MODULE):
                    await asyncio.wait_for(service.stop(), timeout=2)
                assert not release.is_set()  # stop() returned while the write was still hung
            finally:
                release.set()

        assert "Heartbeat write still in flight after stop" in caplog.messages


class TestSendHeartbeat:
    """Test HeartbeatService._send_heartbeat."""

    @patch(f"{MODULE}.set_agent_running")
    @patch(f"{MODULE}.get_agent_status", return_value="RUNNING")
    def test_calls_set_agent_running(
        self, mock_get_status: Mock, mock_set_running: Mock, context: AgentRuntimeContext
    ) -> None:
        assert HeartbeatService(context)._send_heartbeat() is True
        mock_set_running.assert_called_once_with("ws-123", "job-456", "agent-789")

    @patch(f"{MODULE}.set_agent_running")
    @patch(f"{MODULE}.get_agent_status", return_value="RUNNING")
    def test_propagates_exception(
        self, mock_get_status: Mock, mock_set_running: Mock, context: AgentRuntimeContext
    ) -> None:
        mock_set_running.side_effect = Exception("API error")
        service = HeartbeatService(context)

        with pytest.raises(Exception, match="API error"):
            service._send_heartbeat()

    @pytest.mark.parametrize("status", ["INVOKING", "INVOKED", "STOPPING", "UNRESPONSIVE", "IDLE"])
    @patch(f"{MODULE}.set_agent_running")
    @patch(f"{MODULE}.get_agent_status")
    def test_skips_when_not_running(
        self,
        mock_get_status: Mock,
        mock_set_running: Mock,
        status: str,
        context: AgentRuntimeContext,
    ) -> None:
        """The instance can become RUNNING again, so the service skips the beat and goes on."""
        mock_get_status.return_value = status
        assert HeartbeatService(context)._send_heartbeat() is True
        mock_set_running.assert_not_called()

    @pytest.mark.parametrize("status", ["STOPPED", "COMPLETED", "FAILED"])
    @patch(f"{MODULE}.set_agent_running")
    @patch(f"{MODULE}.get_agent_status")
    def test_reports_the_end_on_terminal_status(
        self,
        mock_get_status: Mock,
        mock_set_running: Mock,
        status: str,
        context: AgentRuntimeContext,
    ) -> None:
        mock_get_status.return_value = status
        assert HeartbeatService(context)._send_heartbeat() is False
        mock_set_running.assert_not_called()


class TestHeartbeatLoop:
    """Test the background heartbeat loop."""

    @pytest.mark.asyncio
    async def test_loop_survives_send_failure(self, context: AgentRuntimeContext) -> None:
        service = HeartbeatService(context, interval_minutes=0)  # 0 for fast test

        call_count = 0

        def flaky_send() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _client_error("ThrottlingException")
            return True

        with patch.object(service, "_should_enable", return_value=True), patch.object(
            service, "_send_heartbeat", side_effect=flaky_send
        ):
            await service.start()
            await _wait_until(lambda: call_count >= 2)
            await service.stop()

        assert call_count >= 2  # the loop kept beating after the first send raised

    @pytest.mark.asyncio
    async def test_loop_ends_on_terminal_status(
        self, context: AgentRuntimeContext, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A finished instance is read once more, logged once, and never polled again."""
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(service, "_should_enable", return_value=True), patch(
            f"{MODULE}.get_agent_status", return_value="STOPPED"
        ) as mock_get_status, caplog.at_level(logging.INFO, logger=MODULE):
            await service.start()
            assert service._task is not None
            await asyncio.wait_for(service._task, timeout=5)

        mock_get_status.assert_called_once()
        assert [record.getMessage() for record in _logged(caplog)] == [
            "Agent status is STOPPED, heartbeat ended"
        ]

    @pytest.mark.asyncio
    async def test_loop_ends_on_terminal_resource_error(
        self, context: AgentRuntimeContext, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The platform can refuse the status read of a finished instance outright."""
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(service, "_should_enable", return_value=True), patch(
            f"{MODULE}.get_agent_status", side_effect=_client_error("TerminalResourceException")
        ) as mock_get_status, caplog.at_level(logging.INFO, logger=MODULE):
            await service.start()
            assert service._task is not None
            await asyncio.wait_for(service._task, timeout=5)

        mock_get_status.assert_called_once()
        assert [record.levelno for record in _logged(caplog)] == [logging.INFO]
        assert _logged(caplog)[0].exc_info is None

    @pytest.mark.parametrize("code", PERMANENT_CODES)
    @pytest.mark.asyncio
    async def test_loop_ends_with_one_warning_on_permanent_error(
        self, code: str, context: AgentRuntimeContext, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(service, "_should_enable", return_value=True), patch(
            f"{MODULE}.get_agent_status", return_value="RUNNING"
        ), patch(
            f"{MODULE}.set_agent_running", side_effect=_client_error(code)
        ) as mock_set_running, caplog.at_level(logging.WARNING, logger=MODULE):
            await service.start()
            assert service._task is not None
            await asyncio.wait_for(service._task, timeout=5)

        mock_set_running.assert_called_once()
        assert [record.levelno for record in _logged(caplog)] == [logging.WARNING]
        assert code in caplog.text

    @pytest.mark.asyncio
    async def test_unknown_type_is_rechecked_until_heartbeat(
        self, context: AgentRuntimeContext
    ) -> None:
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(
            service, "_should_enable", side_effect=[None, None, True]
        ) as mock_enable, patch.object(service, "_send_heartbeat", return_value=True) as mock_send:
            await service.start()
            await _wait_until(lambda: mock_send.called)
            await service.stop()

        assert mock_enable.call_count == 3

    @pytest.mark.asyncio
    async def test_loop_exits_when_type_resolves_to_not_heartbeat(
        self, context: AgentRuntimeContext
    ) -> None:
        service = HeartbeatService(context, interval_minutes=0)

        with patch.object(service, "_should_enable", side_effect=[None, None, False]), patch.object(
            service, "_send_heartbeat"
        ) as mock_send:
            await service.start()
            assert service._task is not None
            await asyncio.wait_for(service._task, timeout=5)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_calls_do_not_block_event_loop(self, context: AgentRuntimeContext) -> None:
        """The first lookup, the loop's re-check and the send all run in worker threads."""
        service = HeartbeatService(context, interval_minutes=0)
        lookups = iter([None, True])  # unknown at start, HEARTBEAT on the first re-check
        sent = threading.Event()

        def slow_lookup() -> Optional[bool]:
            time.sleep(0.3)
            return next(lookups)

        def slow_send() -> bool:
            time.sleep(0.3)
            sent.set()
            return True

        gaps: List[float] = []

        async def ticker() -> None:  # a concurrent coroutine; a call on the loop thread stalls it
            while not sent.is_set():
                started = time.monotonic()
                await asyncio.sleep(0.01)
                gaps.append(time.monotonic() - started)

        with patch.object(service, "_should_enable", side_effect=slow_lookup), patch.object(
            service, "_send_heartbeat", side_effect=slow_send
        ):
            ticking = asyncio.create_task(ticker())
            await asyncio.sleep(0)  # let the ticker start before the first lookup
            await service.start()
            await asyncio.wait_for(ticking, timeout=5)  # ends after the first send
            await service.stop()

        assert max(gaps) < 0.2  # each call takes 0.3s
