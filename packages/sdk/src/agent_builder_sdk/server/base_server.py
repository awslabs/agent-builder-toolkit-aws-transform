# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Abstract base server interface.
"""

import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from starlette_context import context as request_context
from strands.telemetry import StrandsTelemetry

from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
)
from agent_builder_sdk.custom_types.orchestrator_agent_types import (
    A2AContext,
    ConversationContext,
    ProcessMessageRequest,
)
from agent_builder_sdk.custom_types.response_types import SendMessageOutput
from agent_builder_sdk.custom_types.server_types import (
    JsonRpcError,
    JsonRpcMethods,
    JsonRpcRequest,
    JsonRpcResponse,
)
from agent_builder_sdk.custom_types.task_types import A2ATask, GetTaskRequest, GetTaskResponse
from agent_builder_sdk.env_var import get_initial_agent_runtime_context_from_env
from agent_builder_sdk.interfaces import StreamingCapable
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.orchestrator_strands.conversation.constants import (
    MessageSourceType,
    classify_source,
)
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.streaming.a2a_frame_utils import STATE_FAILED
from agent_builder_sdk.streaming.raw_a2a_emitter import status_update
from agent_builder_sdk.task_handler import TaskHandler
from agent_builder_sdk.utils import extract_message_info

if TYPE_CHECKING:
    from agent_builder_sdk.streaming.config import StreamingConfig

logger = logging.getLogger(__name__)


class BaseServer(ABC):
    """Abstract base class for all server implementations."""

    app: FastAPI
    initialized: bool
    context: Optional[AgentRuntimeContext]
    notification_handler: Optional[NotificationHandler]
    task_handler: Optional[TaskHandler]
    message_handler: Optional[MessageHandler]
    tracing: Optional[str]
    # Streaming opt-in switch, shared by all servers: None = off. A subclass that supports
    # streaming sets it (AgentRuntimeServer does in __init__) and overrides _build_streaming_runtime.
    streaming_config: Optional["StreamingConfig"] = None

    @abstractmethod
    async def initialize_agent(self, auth_token: Optional[str] = None) -> None:
        pass

    @asynccontextmanager
    async def _lifespan(self, app):
        """FastAPI lifespan context manager - (optional)"""
        yield

    async def _startup(self) -> None:
        """Server startup logic - (optional)"""
        pass

    async def _cleanup(self) -> None:
        """Cleanup all components during shutdown - (optional)"""
        pass

    @abstractmethod
    def start(self) -> None:
        """Start the server (blocking call)."""
        pass

    @staticmethod
    def is_jsonrpc_request(request: Dict[str, Any]) -> bool:
        """Check if request is JSON-RPC format (AgentCore)."""
        return "jsonrpc" in request and "method" in request

    async def ensure_initialized(self, request: Optional[Dict[str, Any]] = None) -> None:
        """Ensure agent is initialized from JSON-RPC request (AgentCore mode only)."""
        if self.initialized:
            logger.info("Agent already initialized. Skipping initialization.")
            return

        # Clear any inconsistent state from previous failed initialization
        if self.context and not self.initialized:
            logger.warning("Clearing inconsistent state from previous failed initialization")
            self.context = None

        # Only AgentCore initialization from request - MDE is already initialized in _startup()
        if request and self.is_jsonrpc_request(request):
            await self.extract_and_initialize(request)
            return

        # If we reach here, it means AgentCore mode but no valid request context
        raise ValueError("Agent not initialized and no valid JSON-RPC request context provided")

    async def extract_and_initialize(self, request: Dict[str, Any]) -> None:
        """Extract initialization context from any request type and initialize."""
        init_request = {}
        params = request.get("params", {})
        method = request.get("method", "")

        if method in [JsonRpcMethods.INVOKE, JsonRpcMethods.RESTORE]:
            # Method 1: Direct invocationContext (invoke/restore)
            invocation_context = params.get("invocationContext", {})
            job_metadata = invocation_context.get("jobMetadata", {})
            agent_metadata = invocation_context.get("agentMetadata", {})
            user_metadata = invocation_context.get("userMetadata", {})
            init_request = {
                "workspaceId": job_metadata.get("workspaceId"),
                "jobId": job_metadata.get("jobId"),
                "agentInstanceId": params.get("agentInstanceId"),
                "agentId": agent_metadata.get("agentId"),
                "agentVersion": agent_metadata.get("agentVersion"),
                "tenantAccountId": user_metadata.get("accountId"),
                "authorizationToken": invocation_context.get("authorizationToken"),
            }

        elif method in [JsonRpcMethods.NOTIFY, JsonRpcMethods.HEALTHCHECK, JsonRpcMethods.STOP]:
            # Method 2: Direct jobMetadata (notify/healthcheck/stop)
            job_metadata = params.get("jobMetadata", {})
            init_request = {
                "workspaceId": job_metadata.get("workspaceId"),
                "jobId": job_metadata.get("jobId"),
                "agentInstanceId": params.get("agentInstanceId"),
                "authorizationToken": params.get("authorizationToken"),
            }

        elif method == JsonRpcMethods.HANDSHAKE:
            # Method 3: No initialization needed for handshake
            return

        elif method == JsonRpcMethods.TASKS_GET:
            # Method 3: tasks/get metadata
            metadata = params.get("metadata", {})
            init_context = metadata.get("agentInitializationContext", {})
            job_metadata = init_context.get("jobMetadata", {})
            init_request = {
                "workspaceId": job_metadata.get("workspaceId"),
                "jobId": job_metadata.get("jobId"),
                "agentInstanceId": init_context.get("agentInstanceId"),
                "authorizationToken": init_context.get("authorizationToken"),
            }

        elif method in (JsonRpcMethods.MESSAGE_SEND, JsonRpcMethods.MESSAGE_STREAM):
            # Method 4: A2A metadata (message/send and its streaming counterpart
            # message/stream — same message shape, same AgentInitializationContext).
            message = params.get("message", {})
            metadata = message.get("metadata", {})
            init_context = metadata.get("ATX_A2A.AgentInitializationContext", {})
            if init_context:
                job_metadata = init_context.get("jobMetadata", {})
                init_request = {
                    "workspaceId": job_metadata.get("workspaceId"),
                    "jobId": job_metadata.get("jobId"),
                    "agentInstanceId": init_context.get("agentInstanceId"),
                    "authorizationToken": init_context.get("authorizationToken"),
                }

        if init_request and all(
            [
                init_request.get("workspaceId"),
                init_request.get("jobId"),
                init_request.get("agentInstanceId"),
            ]
        ):
            # Extract locale from invocationContext.userMetadata (injected by Compute AgentCoreMapper)
            invocation_context = params.get("invocationContext", {})
            user_metadata = invocation_context.get("userMetadata", {})
            locale = user_metadata.get("invocationUserCurrentLocale")
            if locale:
                logger.info("Locale configured: %s", locale)

            # Set context in class
            self.context = AgentRuntimeContext(
                workspace_id=init_request["workspaceId"],
                job_id=init_request["jobId"],
                agent_instance_id=init_request["agentInstanceId"],
                agent_id=init_request.get("agentId"),
                agent_version=init_request.get("agentVersion"),
                tenant_account_id=init_request.get("tenantAccountId"),
                initial_auth_token=init_request.get("authorizationToken"),
                locale=locale,
            )

            # Initialize with token
            await self.initialize_agent(self.context.initial_auth_token)
        else:
            logger.error("Could not extract initialization context from JSON-RPC request")
            raise ValueError("Missing required initialization context in JSON-RPC request")

    async def handle_jsonrpc(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC 2.0 formatted requests for both Bedrock AgentCore and ATX compatibility."""
        try:
            request = JsonRpcRequest(**request_dict)
            logger.info(
                f"Received JSON-RPC request[id={request_dict.get('id')}, method={request.method}]"
            )

            result: Optional[Dict[str, Any] | A2ATask | A2AError] = None
            match request.method:
                case JsonRpcMethods.INVOKE:
                    result = None
                case JsonRpcMethods.HEALTHCHECK:
                    result = {"agentHealth": "HEALTHY"}
                case JsonRpcMethods.HANDSHAKE:
                    logger.info("Handshake request received")
                    result = {"status": "ok"}
                case JsonRpcMethods.NOTIFY:
                    result = await self.handle_notify(request.params or {})
                case JsonRpcMethods.RESTORE:
                    result = None
                case JsonRpcMethods.STOP:
                    # Run cleanup before stopping agent to ensure final checkpoint
                    if hasattr(self, "_cleanup"):
                        await self._cleanup()
                    if hasattr(self, "handle_stop"):
                        result = await self.handle_stop(request.params or {})
                    else:
                        result = None
                    self.stop_requested = True
                case JsonRpcMethods.MESSAGE_SEND:
                    result = await self.handle_message_send(request.params or {}, request.id)
                case JsonRpcMethods.TASKS_GET:
                    result = await self.handle_tasks_get(request.params or {})
                case _:
                    return JsonRpcResponse(
                        error=JsonRpcError.METHOD_NOT_FOUND, id=request.id
                    ).model_dump()
            logger.info(
                f"Successfully handled request[id={request_dict.get('id')}, method={request.method}]"
            )
            return JsonRpcResponse(result=result, id=request.id).model_dump()

        except Exception as e:
            logger.error(f"Error handling JSON-RPC request: {e}")
            return JsonRpcResponse(
                error={**JsonRpcError.INTERNAL_ERROR, "message": str(e)}, id=request_dict.get("id")
            ).model_dump()

    async def handle_notify(self, params: Dict[str, Any]):
        """Handle notification - override in subclasses if needed."""
        if hasattr(self, "notification_handler") and self.notification_handler:
            notification = params.get("notification", {})
            return await self.notification_handler.handle_notification(notification)
        return None

    async def handle_message_send(self, params: Dict[str, Any], request_id):
        """Handle message send - common implementation."""
        message = A2AMessage(**params.get("message", {}))
        if request_context.exists():
            request_context["a2a"] = {
                "message": {
                    "context_id": message.contextId,
                    "id": message.messageId,
                    "role": message.role,
                    "task_id": message.taskId,
                }
            }

        invocation_request = InvocationRequest(message)
        if self.message_handler is None:
            return None
        else:
            send_result = await self.message_handler.send_message(invocation_request)
            if send_result.error:
                # Raise exception to be caught by main handler
                raise Exception(f"Message send failed: {send_result.error.message}")
            return send_result.result.to_dict() if send_result.result else None

    def _setup_streaming(self) -> None:
        """Stand up streaming if opted in. Called once during init by every server.

        No-op when off (streaming_config is None), so a server that doesn't support streaming
        does nothing. When on, delegates the concrete runtime (pool, shared client, hooks) to
        _build_streaming_runtime, which the supporting server overrides.
        """
        if self.streaming_config is None:
            return
        self._build_streaming_runtime()

    def _build_streaming_runtime(self) -> None:
        """Build the concrete streaming runtime (pool, shared MCP client, per-agent hooks).

        Overridden by servers that support streaming. The base raises so a server that sets a
        streaming_config without implementing the runtime fails fast at init, not mid-stream.
        """
        raise NotImplementedError("This server does not support streaming")

    async def _get_agent_for_streaming(self, source_id: str, source_type: MessageSourceType):
        """Return the agent instance to serve a streaming turn for ``source_id``.

        Overridden per server type. The base raises so a server that hasn't opted into
        streaming rejects the request rather than serving it silently.
        """
        raise NotImplementedError("This server does not support streaming")

    def _get_streaming_config(self) -> Optional["StreamingConfig"]:
        """The streaming config shaping this turn's emitted categories, or None when off."""
        return self.streaming_config

    @asynccontextmanager
    async def _streaming_turn_lease(self, source_id: str) -> AsyncIterator[None]:
        """Hold a lease for the full duration of a streaming turn so the server can protect
        the source's agent from eviction while it streams. Base is a no-op; servers with an
        evictable per-source agent pool override this to mark the source in-flight."""
        yield

    async def _handle_streaming(self, params: Dict[str, Any]) -> StreamingResponse:
        """Serve one message/stream turn as an SSE stream of A2A frames.

        Parses the A2A message (same shape as message/send), resolves the ready agent,
        and streams ``process_message_stream`` — each A2A frame becomes one
        ``data: {json}\\n\\n`` SSE event. Runs inline (no request queue): the connection
        is held for the whole turn.
        """
        message = A2AMessage(**params.get("message", {}))

        # Build the agent input identically to the message/send path: reuse
        # extract_message_info (the single source of truth) so the SAME A2A message produces
        # the SAME agent input on both paths. message/send serializes the full parts list
        # (text + data + file, first part's "kind"->"type" normalized) and passes
        # json.dumps(parts); message/stream must too, or data/file parts (e.g. attachments)
        # would reach the agent on message/send but silently vanish on message/stream.
        message_info = extract_message_info(InvocationRequest(message))
        message_body = json.dumps(message_info.parts)
        user_id, sender = message_info.user_id, message_info.sender

        conv_context = ConversationContext(
            user_id=user_id,
            agent_instance_id=sender,
            a2a_context=A2AContext(context_id=message.contextId, task_id=message.taskId),
        )

        # Key the per-source agent by the SAME classification a turn is processed with
        # (neutral helper — no dependency on any concrete agent class).
        source_id, source_type = classify_source(conv_context)

        # A stable conversation id derived from the caller's identity (this agent is
        # job-scoped, so a user's turns share one conversation) — it becomes the wire
        # threadId. The task/run id is minted by the agent (the A2A server owns Task ids),
        # not taken from the request. The response-persist leg routes on message.contextId
        # (carried on conv_context), independently of these wire ids.
        conversation_id = self._build_conversation_id(user_id)
        logger.info(
            "Streaming turn: source_type=%s userId=%s agentInstanceId=%s conversation=%s context=%s",
            source_type.value,
            user_id,
            sender,
            conversation_id,
            message.contextId,
        )
        agent = await self._get_agent_for_streaming(source_id, source_type)

        # contextId requirement is the agent's policy, not the transport's: an orchestrator
        # persists its reply to Chat keyed by contextId, so it requires one; a sub-agent replies
        # to another agent and does not. Raise before the SSE response starts so a missing-required
        # contextId surfaces as a JSON-RPC error to the caller, not a user-visible stream frame.
        if (
            isinstance(agent, StreamingCapable)
            and agent.requires_context_id()
            and not message.contextId
        ):
            raise ValueError("contextId is required for a streaming (message/stream) turn")

        req = ProcessMessageRequest(message_body, conv_context)

        streaming_config = self._get_streaming_config()

        async def gen():
            # Track the turn's wire ids so a fallback terminal (below) can reuse them.
            task_id: Optional[str] = None
            context_id_seen: Optional[str] = None
            # Hold the in-flight lease for the WHOLE turn so the source's per-user agent can't
            # be idle-evicted mid-stream (no-op unless the server has an evictable pool).
            async with self._streaming_turn_lease(source_id):
                # cfg is passed only when the server has one, so the orchestrator keeps its
                # DEFAULT_STREAMING_CONFIG default otherwise (base servers have no config).
                stream_kwargs = {} if streaming_config is None else {"cfg": streaming_config}
                try:
                    async for frame in agent.process_message_stream(
                        req, conversation_id=conversation_id, **stream_kwargs
                    ):
                        if task_id is None:
                            task_id = frame.get("id") or frame.get("taskId")
                        if context_id_seen is None:
                            context_id_seen = frame.get("contextId")
                        # default=str is a serialization backstop: a stray non-serializable value
                        # degrades to its repr instead of aborting the stream with no terminal.
                        yield f"data: {json.dumps(frame, default=str)}\n\n"
                except Exception:
                    # A failure escaping process_message_stream (or the serialize/yield above) would
                    # otherwise drop the connection with NO terminal frame — the client can't tell a
                    # clean finish from a crash. Emit one terminal failed frame so every stream ends
                    # with a terminal, whatever went wrong. (Serialization errors are now prevented
                    # upstream by the emitter's projection + default=str; this guards the rest.)
                    logger.exception(
                        "Streaming turn failed during emission; emitting terminal failed frame"
                    )
                    # Reuse the turn's task/context ids; carry no message (DataPart shape is
                    # path-specific — raw A2A vs AG-UI), the failed/final state is enough to end.
                    terminal = status_update(
                        task_id or str(uuid.uuid4()), context_id_seen, STATE_FAILED, final=True
                    )
                    yield f"data: {json.dumps(terminal)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    def _build_conversation_id(self, user_id: Optional[str]) -> str:
        """Build a stable id for the user's conversation on a streaming turn, so every turn
        of one conversation groups together on the client.

        ``<userId>[#<workspaceId>[#<jobId>]]`` — these are the identity parts that reliably
        reach the agent on the wire (userId from source-information, workspace/job from the
        init context). workspace/job are appended only when present, and job only when a
        workspace is (a job never exists without its workspace). This is a job-scoped agent,
        so userId + workspace + job uniquely identifies the conversation.
        """
        parts = [user_id or ""]
        if self.context and self.context.workspace_id:
            parts.append(self.context.workspace_id)
            if self.context.job_id:
                parts.append(self.context.job_id)
        return "#".join(parts)

    async def handle_tasks_get(self, params: Dict[str, Any]) -> A2ATask | A2AError:
        """Handle tasks/get - common implementation."""
        task_id = params.get("id")
        if not task_id:
            return A2AError(
                code=A2AErrorCode.INVALID_REQUEST, message="Missing required parameter: id"
            )

        task_request = GetTaskRequest(id=task_id)
        task_response = await self.get_task(task_request)

        # Return task or error based on response
        if task_response.error:
            return task_response.error

        if not task_response.result:
            return A2AError(code=A2AErrorCode.INTERNAL_ERROR, message="Task not found")

        return task_response.result

    async def _initialize_mde_mode(self) -> None:
        """Initialize agent for MDE mode from environment variables."""
        self.context = get_initial_agent_runtime_context_from_env()
        await self.initialize_agent(self.context.initial_auth_token)

    def setup_common_routes(self) -> None:
        """Setup common routes shared by all server implementations."""

        @self.app.get("/ping")
        async def ping():
            """
            Returns a status code indicating your agent's health. If your agent needs to process background tasks,
            you can indicate it with the /ping status. If the ping status is HealthyBusy,
            the runtime session is considered active.

            ref: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
            :return:
                status:
                    Healthy - System is ready to accept new work
                    HealthyBusy - System is operational but currently busy with async tasks
                time_of_last_update
                    Used to determine how long the system has been in its current state
            """
            return {"status": "Healthy" if self.stop_requested else "HealthyBusy"}

        @self.app.post("/invocations", response_model=None)
        async def handle_invocations(request: Dict[str, Any]) -> Dict[str, Any] | StreamingResponse:
            """Handle AgentCore JSON-RPC, MDE notifications, and message/stream (SSE).

            ``response_model=None``: the return is either a JSON dict or a
            StreamingResponse, which FastAPI cannot build a response model from.
            """
            if request_context.exists() and self.is_jsonrpc_request(request):
                request_context["rpc"] = {
                    "request": {
                        "id": request.get("id"),
                        "method": request.get("method"),
                    }
                }

            try:
                logger.info("Received invocation request")
                logger.debug(f"Full request details: {request}")

                await self.ensure_initialized(request)

                # message/stream is a streaming turn: it needs an SSE StreamingResponse,
                # not a JSON-RPC dict, so it is peeled off before handle_jsonrpc. Every
                # other method (message/send, tasks/get, notify, ...) is unchanged. Without a
                # StreamingConfig it falls through to handle_jsonrpc's -32601 Method not found,
                # the answer before streaming existed.
                if (
                    request.get("method") == JsonRpcMethods.MESSAGE_STREAM
                    and self.streaming_config is not None
                ):
                    return await self._handle_streaming(request.get("params") or {})

                if self.is_jsonrpc_request(request):
                    return await self.handle_jsonrpc(request)
                else:
                    return await self.handle_mde_notification(request)

            except Exception as e:
                logger.error(f"Error handling invocation: {e}")
                return self.format_error_response(request, e)

        # REST endpoints for MDE compatibility
        @self.app.post("/message/send")
        async def send_message_rest(request: InvocationRequest) -> SendMessageOutput:
            """REST endpoint for message sending (MDE mode - agent already initialized)."""
            if request_context.exists():
                request_context["a2a"] = {
                    "message": {
                        "context_id": request.message.contextId,
                        "id": request.message.messageId,
                        "role": request.message.role,
                        "task_id": request.message.taskId,
                    }
                }

            logger.debug("Received %s", request)

            if self.message_handler is None:
                return SendMessageOutput(
                    error=A2AError(
                        code=A2AErrorCode.INTERNAL_ERROR,
                        message="Message handler not available",
                    )
                )
            return await self.message_handler.send_message(request)

        @self.app.post("/tasks/get")
        async def get_task_rest(request: GetTaskRequest) -> GetTaskResponse:
            """REST endpoint for task retrieval (MDE mode - agent already initialized)."""
            return await self.get_task(request)

        @self.app.post("/message/stream", response_model=None)
        async def message_stream_rest(
            request: Dict[str, Any],
        ) -> StreamingResponse | Dict[str, Any]:
            """REST endpoint for streaming (MDE mode). Same params shape as the AgentCore
            message/stream method; delegates to the shared _handle_streaming helper.

            ``response_model=None``: returns a StreamingResponse (SSE), not a model.
            """
            # Without a StreamingConfig, 404 as before this route existed.
            if self.streaming_config is None:
                raise HTTPException(status_code=404)
            # A failure before the stream starts (e.g. the agent never became ready) is an error
            # body, as on /invocations, not an uncaught 500.
            try:
                return await self._handle_streaming(request.get("params") or request)
            except Exception as e:
                logger.error(f"Error handling message/stream: {e}")
                return self.format_error_response(request, e)

    async def handle_mde_notification(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MDE notification - implementation varies by server type."""
        raise NotImplementedError(
            "MDE notifications are not supported by this server implementation"
        )

    def format_error_response(self, request: Dict[str, Any], error: Exception) -> Dict[str, Any]:
        if self.is_jsonrpc_request(request):
            return JsonRpcResponse(
                error={**JsonRpcError.INTERNAL_ERROR, "message": str(error)},
                id=request.get("id"),
            ).model_dump()
        else:
            return {"error": str(error)}

    async def get_task(self, request: GetTaskRequest) -> GetTaskResponse:
        """Process a task retrieval request."""
        logger.info(f"GetTask request received for task: {request.id}")

        try:
            if self.task_handler is None:
                raise ValueError("Task handler not initialized")
            response = await self.task_handler.get_task(request)
            logger.info(
                f"GetTask completed for task_id: {request.id}, status: {'success' if response.result else 'error'}"
            )
            return response
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error processing GetTask request: {error_msg}")
            return GetTaskResponse(
                error=A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR,
                    message="Internal error getting task details",
                )
            )

    def setup_tracing(self, tracing: str) -> None:
        """Setup tracing based on tracing type configuration."""
        tracing_endpoint = "http://localhost:4318"

        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = tracing_endpoint
        strands_telemetry = StrandsTelemetry()
        strands_telemetry.setup_otlp_exporter()

        if tracing == "local":
            logger.info(f"Setting up local Jaeger tracing at: {tracing_endpoint}")
            strands_telemetry.setup_console_exporter()

        logger.info(f"{tracing} tracing configured for endpoint")
