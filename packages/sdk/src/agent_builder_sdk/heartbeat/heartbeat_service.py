# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Heartbeat service that periodically signals agent liveness to the platform.

When the agent's monitoring type is HEARTBEAT (configured in the ATX Agent Registry),
this service calls UpdateAgentInstance(RUNNING) every 5 minutes to signal liveness
to the platform's health monitoring.
"""

import asyncio
import logging
from typing import Optional

from agent_builder_sdk.agentic_framework.agent_lifecycle import (
    get_agent_status,
    set_agent_running,
)
from agent_builder_sdk.agentic_framework.agentic_api_helper import get_agent_registry
from agent_builder_sdk.agentic_framework.client_factory import get_agentic_api_client
from agent_builder_sdk.custom_types.agent_registry_types import MonitoringType
from agent_builder_sdk.server.server_models import AgentRuntimeContext

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_MINUTES = 5


class HeartbeatService:
    """Periodically emits heartbeat (update_agent_instance RUNNING) to the platform."""

    def __init__(
        self, context: AgentRuntimeContext, interval_minutes: int = HEARTBEAT_INTERVAL_MINUTES
    ):
        self._context = context
        self._interval_seconds = interval_minutes * 60
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Check monitoring type and start heartbeat loop if HEARTBEAT is configured."""
        if not self._should_enable():
            return

        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat service started (interval: {self._interval_seconds}s)")

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                # Cancellation is the expected shutdown path for the heartbeat task; nothing to clean up.
                pass
            logger.info("Heartbeat service stopped")

    def _should_enable(self) -> bool:
        """Check if heartbeat monitoring is configured for this agent."""
        if not self._context.agent_id:
            logger.debug("Heartbeat skipped: no agent_id in context")
            return False

        try:
            registry = get_agent_registry(
                workspace_id=self._context.workspace_id,
                job_id=self._context.job_id,
                agent_instance_id=self._context.agent_instance_id,
                client=get_agentic_api_client(),
            )
            request = registry._inject_request_context({"name": self._context.agent_id})
            if self._context.agent_version:
                request["version"] = self._context.agent_version
            response = registry.client.get_agent_version(**request)

            configuration = response.get("configuration") or {}
            monitoring_type = configuration.get("monitoringType")

            if monitoring_type == MonitoringType.HEARTBEAT.value:
                logger.info(f"Heartbeat monitoring enabled for agent {self._context.agent_id}")
                return True

            logger.debug(f"Heartbeat not configured (monitoringType={monitoring_type})")
            return False
        except Exception as e:
            logger.warning(f"Failed to check monitoring type for {self._context.agent_id}: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """Background loop that sends heartbeat every interval."""
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                self._send_heartbeat()
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

        set_agent_running(
            self._context.workspace_id,
            self._context.job_id,
            self._context.agent_instance_id,
        )
        logger.info("Heartbeat sent successfully")
