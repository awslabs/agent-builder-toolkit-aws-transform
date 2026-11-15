# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hook that records the customer deliverables a turn verifies, for the reply to link."""

import logging
from typing import Any

from strands.hooks.events import AfterToolCallEvent, BeforeInvocationEvent
from strands.hooks.registry import HookProvider, HookRegistry

from agent_builder_sdk.ui_chat.artifact_delivery import (
    DELIVERED_ARTIFACTS_STATE_KEY,
    delivered_artifacts_in_tool_result,
)

logger = logging.getLogger(__name__)


class ArtifactDeliveryHookProvider(HookProvider):
    """Collects the customer deliverables the turn verifies on ``agent.state`` for the replies.

    ``agent.state`` outlives the turn on a reused agent, so the list is reset at the start of each
    invocation. The queue request handler and the streaming persist hook read it and append
    deeplinks to the reply of a user turn; without this hook they add nothing.

    Install it on every orchestrator agent that answers users. The tool-name match is exact
    (``get_artifact_metadata``), so an MCP client mounted with a tool prefix records nothing.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._reset)
        registry.add_callback(AfterToolCallEvent, self._on_tool_result)

    def _reset(self, event: BeforeInvocationEvent) -> None:
        event.agent.state.set(DELIVERED_ARTIFACTS_STATE_KEY, [])

    def _on_tool_result(self, event: AfterToolCallEvent) -> None:
        try:
            verified = delivered_artifacts_in_tool_result(event.tool_use["name"], event.result)
            if not verified:
                return
            recorded = event.agent.state.get(DELIVERED_ARTIFACTS_STATE_KEY)
            delivered = (
                [item for item in recorded if isinstance(item, dict)]
                if isinstance(recorded, list)
                else []
            )
            seen = {item.get("artifact_id") for item in delivered}
            for item in verified:
                if item["artifact_id"] not in seen:
                    delivered.append(item)
                    seen.add(item["artifact_id"])
            event.agent.state.set(DELIVERED_ARTIFACTS_STATE_KEY, delivered)
            logger.info("Turn delivered %d user-visible artifact(s)", len(delivered))
        except Exception:
            logger.exception("Failed to record a delivered artifact; the turn continues")
