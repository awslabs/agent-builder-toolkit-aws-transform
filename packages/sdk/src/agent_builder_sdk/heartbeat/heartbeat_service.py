# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Heartbeat service that periodically signals agent liveness to the platform.

When the agent's monitoring type is HEARTBEAT (configured in the ATX Agent Registry),
this service calls UpdateAgentInstance(RUNNING) every 5 minutes, while the instance is
RUNNING, to signal liveness to the platform's health monitoring. It ends by itself when
the instance reaches a terminal status or a call fails with a permanent error.
"""

import asyncio
import logging
import threading
from typing import Optional

from botocore.exceptions import ClientError

from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_agent_instance_manager_with_context,
    get_agent_status,
    set_agent_running,
)
from agent_builder_sdk.agentic_framework.agentic_api_helper import get_agent_registry
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.constants import NON_RETRYABLE_ERROR_CODES
from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.server.server_models import AgentRuntimeContext

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_MINUTES = 5
# How long stop() waits for a RUNNING write that is already on the wire.
STOP_TIMEOUT_SECONDS = 10
# An instance never leaves these statuses, so there is nothing left to signal.
_TERMINAL_STATUSES = frozenset({"STOPPED", "COMPLETED", "FAILED"})
# The platform answers with this code for an instance (or its job) in a terminal status.
_TERMINAL_ERROR_CODE = "TerminalResourceException"


def _is_final(error: Exception) -> bool:
    """Return True, after one log line, when no later call can succeed after ``error``."""
    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code")
    if code == _TERMINAL_ERROR_CODE:
        logger.info(f"Agent instance is in a terminal status, heartbeat ended: {error}")
        return True
    if code in NON_RETRYABLE_ERROR_CODES:
        logger.warning(f"Heartbeat ended, {code} is not retryable: {error}")
        return True
    return False


class HeartbeatService:
    """Periodically emits heartbeat (update_agent_instance RUNNING) to the platform."""

    def __init__(
        self, context: AgentRuntimeContext, interval_minutes: int = HEARTBEAT_INTERVAL_MINUTES
    ) -> None:
        self._context = context
        self._interval_seconds = interval_minutes * 60
        self._task: Optional[asyncio.Task] = None
        # Worker threads outlive a cancelled task. They check _stopped under _write_lock (a beat
        # right before its RUNNING write, the lookup before it reports a start); stop() sets the
        # flag, then takes the lock.
        self._stopped = threading.Event()
        self._write_lock = threading.Lock()

    async def start(self) -> None:
        """Start the background task and return at once.

        The task reads the monitoring type itself, so the caller does not wait for the
        registry. It beats only when the type is HEARTBEAT. One instance runs one task: a
        later call does nothing, also after stop().
        """
        if self._task is None:
            self._task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop the heartbeat background task.

        A beat that has not written yet skips its RUNNING write, and a write already in
        flight is waited for (up to STOP_TIMEOUT_SECONDS), so the heartbeat does not
        overwrite a status the caller sets next (such as STOPPED).
        """
        self._stopped.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                # Cancellation is the expected shutdown path for the heartbeat task; nothing to clean up.
                pass
            # Cancelling does not stop a beat already running in its worker thread. If it has
            # not written yet it sees _stopped and skips; wait out a write already on the wire.
            if not await asyncio.to_thread(self._wait_for_write):
                logger.warning("Heartbeat write still in flight after stop")
            logger.info("Heartbeat service stopped")

    def _wait_for_write(self) -> bool:
        # Bounded so a hung call cannot stall shutdown; a write slower than STOP_TIMEOUT_SECONDS
        # can still land after the caller's next status update. Acquire and release in this
        # thread, so a cancelled stop() cannot leave the lock held.
        if not self._write_lock.acquire(timeout=STOP_TIMEOUT_SECONDS):
            return False
        self._write_lock.release()
        return True

    def _should_enable(self) -> Optional[bool]:
        """Check if heartbeat monitoring is configured for this agent.

        Returns True for HEARTBEAT, False when the service has nothing to do (any other
        monitoring type, a terminal instance, a permanent API error), or None if the
        lookup failed and the caller should retry later.
        """
        agent_id, agent_version = self._context.agent_id, self._context.agent_version
        try:
            if not (agent_id and agent_version):
                # Only invoke/restore requests carry agent metadata; the instance knows both.
                # Without a version the registry answers for the latest one, which can differ
                # from the version this instance runs.
                instance = get_agent_instance_manager_with_context(
                    self._context.workspace_id,
                    self._context.job_id,
                    self._context.agent_instance_id,
                ).get_status(self._context.agent_instance_id)
                agent_id = agent_id or instance.get("agentId")
                agent_version = agent_version or instance.get("agentVersion")
                if not agent_id:
                    logger.info("Heartbeat disabled: agent instance has no agentId")
                    return False

            registry = get_agent_registry(
                workspace_id=self._context.workspace_id,
                job_id=self._context.job_id,
                agent_instance_id=self._context.agent_instance_id,
                client=get_agentic_api_client(),
            )
            configuration = registry.get_agent_configuration(agent_id, agent_version)
            monitoring_type = configuration.get("monitoringType")

            if monitoring_type == MonitoringType.HEARTBEAT.value:
                with self._write_lock:
                    if not self._stopped.is_set():
                        logger.info(f"Heartbeat monitoring enabled for agent {agent_id}")
                        logger.info(
                            f"Heartbeat service started (interval: {self._interval_seconds}s)"
                        )
                return True

            logger.info(f"Heartbeat disabled: monitoringType={monitoring_type}")
            return False
        except Exception as e:
            if _is_final(e):
                return False
            logger.warning(f"Failed to check monitoring type, will retry: {e}")
            return None

    async def _heartbeat_loop(self) -> None:
        """Background loop: resolve the monitoring type, then beat every interval.

        While the type is unknown (None), each tick re-checks it. The loop exits once the
        type resolves to anything other than HEARTBEAT, the instance reaches a terminal
        status, or a call fails with a permanent error.
        """
        enabled = await asyncio.to_thread(self._should_enable)
        while enabled is not False:
            await asyncio.sleep(self._interval_seconds)
            if enabled is None:
                enabled = await asyncio.to_thread(self._should_enable)
            if enabled:
                try:
                    enabled = await asyncio.to_thread(self._send_heartbeat)
                except Exception as e:
                    if _is_final(e):
                        return
                    logger.warning("Heartbeat failed", exc_info=True)

    def _send_heartbeat(self) -> bool:
        """Call set_agent_running when the agent is RUNNING; skip any other status.

        Returns False when there will be no further beat (terminal status or stop()).
        """
        status = get_agent_status(
            self._context.workspace_id,
            self._context.job_id,
            self._context.agent_instance_id,
        )
        if status in _TERMINAL_STATUSES:
            logger.info(f"Agent status is {status}, heartbeat ended")
            return False
        if status != "RUNNING":
            logger.info(f"Agent status is {status}, skipping heartbeat")
            return True

        with self._write_lock:
            if self._stopped.is_set():
                logger.info("Heartbeat service stopped, skipping heartbeat")
                return False
            set_agent_running(
                self._context.workspace_id,
                self._context.job_id,
                self._context.agent_instance_id,
            )
        logger.info("Heartbeat sent successfully")
        return True
