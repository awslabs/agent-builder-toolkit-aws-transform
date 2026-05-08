import uuid
from datetime import datetime

import agent_builder_types.literals as lit
import agent_builder_types.type_defs as abt
from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_types import TransformAgenticServiceClient


class HitlClient(AgenticApiHelper):
    """A wrapper around AWS Transform's HITL (human-in-the-loop) APIs."""

    client: TransformAgenticServiceClient

    async def create_hitl_task(
        self,
        ux_component_id: str,
        description: str,
        title: str,
        severity: lit.SeverityType = "STANDARD",
        hitl_task_type: lit.HitlTaskTypeType = "NORMAL",
        step_id: str | None = None,
        blocking_type: lit.BlockingTypeType | None = None,
        hitl_request_artifact: abt.HitlTaskArtifactTypeDef | None = None,
        expired_at: datetime | str | None = None,
        tag: str | None = None,
    ) -> abt.CreateHitlTaskResponseTypeDef:
        request: abt.CreateHitlTaskRequestRequestTypeDef = {
            "uxComponentId": ux_component_id,
            "description": description,
            "title": title,
            "severity": severity,
            "hitlTaskType": hitl_task_type,
            "idempotencyToken": str(uuid.uuid4()),
            "requestContext": self._create_request_context(),
        }

        if step_id is not None:
            request["stepId"] = step_id

        if blocking_type is not None:
            request["blockingType"] = blocking_type

        if hitl_request_artifact is not None:
            request["hitlRequestArtifact"] = hitl_request_artifact

        if expired_at is not None:
            request["expiredAt"] = expired_at

        if tag is not None:
            request["tag"] = tag

        return self.client.create_hitl_task(**request)

    async def get_hitl_task(self, hitl_task_id: str) -> abt.GetHitlTaskResponseTypeDef:
        request: abt.GetHitlTaskRequestRequestTypeDef = {
            "hitlTaskId": hitl_task_id,
            "requestContext": self._create_request_context(),
        }

        return self.client.get_hitl_task(**request)

    async def start_hitl_task(
        self, hitl_task_id: str, first_in_chain: bool | None = None
    ) -> abt.StartHitlTaskResponseTypeDef:
        request: abt.StartHitlTaskRequestRequestTypeDef = {
            "hitlTaskId": hitl_task_id,
            "idempotencyToken": str(uuid.uuid4()),
            "requestContext": self._create_request_context(),
        }

        if first_in_chain is not None:
            request["firstInChain"] = first_in_chain

        return self.client.start_hitl_task(**request)

    async def close_hitl_task(
        self, hitl_task_id: str, closure_type: lit.ClosureTypeType | None = None
    ) -> abt.CloseHitlTaskResponseTypeDef:
        request: abt.CloseHitlTaskRequestRequestTypeDef = {
            "hitlTaskId": hitl_task_id,
            "idempotencyToken": str(uuid.uuid4()),
            "requestContext": self._create_request_context(),
        }

        if closure_type is not None:
            request["closureType"] = closure_type

        return self.client.close_hitl_task(**request)

    async def list_hitl_tasks(
        self,
        task_type: lit.HitlTaskTypeType,
        task_filter: abt.HitlTaskFilterTypeDef,
        next_token: str,
        max_results: int,
    ) -> abt.ListHitlTasksResponseTypeDef:
        request: abt.ListHitlTasksRequestRequestTypeDef = {
            "taskType": task_type,
            "taskFilter": task_filter,
            "nextToken": next_token,
            "maxResults": max_results,
            "requestContext": self._create_request_context(),
        }

        return self.client.list_hitl_tasks(**request)
