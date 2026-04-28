__all__ = ("ApprovableTools", "requires_approval")

import functools
import json
import logging
from abc import ABCMeta
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Concatenate, ParamSpec, TypeVar

from agent_builder_sdk.agentic_framework.artifact_store import ArtifactStore
from agent_builder_sdk.agentic_framework.common import calculate_digest
from agent_builder_sdk.agentic_framework.hitl import HitlClient
from agent_builder_sdk.custom_types.notification_types import HitlTaskStatus
from agent_builder_sdk.notification import HitlNotifier

P = ParamSpec("P")
R = TypeVar("R", covariant=True)
Self = TypeVar("Self", bound="ApprovableTools")
Tool = Callable[Concatenate[Self, P], Awaitable[R]]

log = logging.getLogger(__name__)


class ApprovableTools(metaclass=ABCMeta):
    """A base class to support tools that use the requires_approval decorator.

    Tools using the requires_approval decorator must be defined in a class that inherits this.
    """

    def __init__(
        self, artifact_store: ArtifactStore, hitl_client: HitlClient, hitl_notifier: HitlNotifier
    ):
        self._artifact_store = artifact_store
        self._hitl_client = hitl_client
        self._hitl_notifier = hitl_notifier


def requires_approval(
    name: str,
    description: str,
    component_id: str,
    properties_callback: Callable[Concatenate[str, str, P], Mapping[str, Any]],
) -> Callable[[Tool[Self, P, R]], Tool[Self, P, R]]:
    """Intercept a Strands tool call to require approval from a human before proceeding.

    Start a HITL task and wait for the HITL to be SUBMITTED before calling the tool.
    This decorator should go before (below) the @tool decorator.

    Requirements:
        - Define the tool in a subclass of ApprovableTools.
        - If using AgentRuntimeServer, use_hitl_notifier must be true when instantiating it.

    Args:
        name: Customer-facing name for the action
        description: Customer-facing description for the action
        component_id: HITL component ID to present the approval
        properties_callback: Function which accepts the name, description, and tool args/kwargs,
            and returns properties for the HITL component

    Returns:
        A decorator.
    """

    def decorator(tool: Tool[Self, P, R]) -> Tool[Self, P, R]:
        @functools.wraps(tool)
        async def wrapper(self: Self, *args: P.args, **kwargs: P.kwargs) -> R:
            try:
                step_id = None

                properties = properties_callback(name, description, *args, **kwargs)
                artifact_id = _upload_hitl_json_artifact(self._artifact_store, properties, step_id)
                log.info("Uploaded HITL JSON artifact %s for %r", artifact_id, name)

                create_response = await self._hitl_client.create_hitl_task(
                    ux_component_id=component_id,
                    description=description,
                    title=f"Approve action: {name}",
                    step_id=step_id,
                    hitl_request_artifact={"artifactId": artifact_id},
                )
                hitl_id = create_response["hitlTaskId"]
                log.info("Created HITL %s with artifact %s for %r", hitl_id, artifact_id, name)

                await self._hitl_client.start_hitl_task(hitl_id)
                log.info("Started HITL %s for %r; waiting for SUBMITTED status...", hitl_id, name)

                await self._hitl_notifier.wait(hitl_id, HitlTaskStatus.SUBMITTED)
                log.info("HITL %s was SUBMITTED; calling the %r tool now", hitl_id, name)

                return await tool(self, *args, **kwargs)
            except Exception:
                log.exception(f"Error calling {name!r} tool requiring an approval")
                raise

        return wrapper

    return decorator


def _upload_hitl_json_artifact(
    artifact_store: ArtifactStore, properties: Mapping[str, Any], step_id: str | None = None
) -> str:
    request = {"properties": properties}
    encoded_request = json.dumps(request).encode("utf8")
    digest = calculate_digest(encoded_request)

    return artifact_store.upload_artifact(
        encoded_request,
        digest,
        category_type="HITL_FROM_AGENT",
        file_type="JSON",
        plan_step_id=step_id,
    )
