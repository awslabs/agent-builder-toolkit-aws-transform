# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Heartbeat service that periodically signals agent liveness to the platform.

When the agent's monitoring type is HEARTBEAT (configured in the ATX Agent Registry),
this service calls UpdateAgentInstance(RUNNING) every 5 minutes, while the instance is
RUNNING, to signal liveness to the platform's health monitoring.
"""

import asyncio
import logging
import threading
from typing import Optional

from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_agent_instance_manager_with_context,
    get_agent_status,
    set_agent_running,
)
from agent_builder_sdk.agentic_framework.agentic_api_helper import get_agent_registry
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.server.server_models import AgentRuntimeContext

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_MINUTES = 5
# How long stop() waits for a RUNNING write that is already on the wire.
STOP_TIMEOUT_SECONDS = 10


class HeartbeatService:
    """Periodically emits heartbeat (update_agent_instance RUNNING) to the platform."""

    def __init__(
        self, context: AgentRuntimeContext, interval_minutes: int = HEARTBEAT_INTERVAL_MINUTES
    ):
        self._context = context
        self._interval_seconds = interval_minutes * 60
        self._task: Optional[asyncio.Task] = None
        # A beat checks _stopped under _write_lock right before its RUNNING write.
        self._stopped = threading.Event()
        self._write_lock = threading.Lock()

    async def start(self) -> None:
        """Check monitoring type and start heartbeat loop if HEARTBEAT is configured.

        If the monitoring type can't be looked up yet, the loop starts anyway and
        re-checks it on each tick until it resolves.
        """
        # A worker thread keeps the event loop (and /ping) responsive; agent setup still
        # waits for this lookup before the server reports ready.
        enabled = await asyncio.to_thread(self._should_enable)
        if enabled is False:
            return

        self._task = asyncio.create_task(self._heartbeat_loop(enabled))
        logger.info(f"Heartbeat service started (interval: {self._interval_seconds}s)")

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

        Returns True for HEARTBEAT, False for any other monitoring type, or None
        if the lookup failed (the caller retries later).
        """
        agent_id, agent_version = self._context.agent_id, self._context.agent_version
        try:
            if not agent_id:
                # Only invoke/restore requests carry agent metadata; fall back to the instance.
                instance = get_agent_instance_manager_with_context(
                    self._context.workspace_id,
                    self._context.job_id,
                    self._context.agent_instance_id,
                ).get_status(self._context.agent_instance_id)
                agent_id, agent_version = instance.get("agentId"), instance.get("agentVersion")
                if not agent_id:
                    logger.info("Heartbeat disabled: agent instance has no agentId")
                    return False

            registry = get_agent_registry(
                workspace_id=self._context.workspace_id,
                job_id=self._context.job_id,
                agent_instance_id=self._context.agent_instance_id,
                client=get_agentic_api_client(),
            )
            request = registry._inject_request_context({"name": agent_id})
            if agent_version:
                request["version"] = agent_version
            response = registry.client.get_agent_version(**request)

            configuration = response.get("configuration") or {}
            monitoring_type = configuration.get("monitoringType")

            if monitoring_type == MonitoringType.HEARTBEAT.value:
                logger.info(f"Heartbeat monitoring enabled for agent {agent_id}")
                return True

            logger.info(f"Heartbeat disabled: monitoringType={monitoring_type}")
            return False
        except Exception as e:
            logger.warning(f"Failed to check monitoring type, will retry: {e}")
            return None

    async def _heartbeat_loop(self, enabled: Optional[bool]) -> None:
        """Background loop that sends heartbeat every interval.

        While the monitoring type is unknown (None), each tick re-checks it instead;
        the loop exits once it resolves to anything other than HEARTBEAT.
        """
        while True:
            await asyncio.sleep(self._interval_seconds)
            if enabled is None:
                enabled = await asyncio.to_thread(self._should_enable)
                if enabled is False:
                    return
            if enabled:
                try:
                    await asyncio.to_thread(self._send_heartbeat)
                except Exception:
                    logger.warning("Heartbeat failed", exc_info=True)

    def _send_heartbeat(self) -> None:
        """Send heartbeat by calling set_agent_running. Skips if agent is not RUNNING."""
        status = get_agent_status(
            self._context.workspace_id,
            self._context.job_id,
            self._context.agent_instance_id,
        )
        if status != "RUNNING":
            logger.info(f"Agent status is {status}, skipping heartbeat")
            return

        with self._write_lock:
            if self._stopped.is_set():
                logger.info("Heartbeat service stopped, skipping heartbeat")
                return
            set_agent_running(
                self._context.workspace_id,
                self._context.job_id,
                self._context.agent_instance_id,
            )
        logger.info("Heartbeat sent successfully")
