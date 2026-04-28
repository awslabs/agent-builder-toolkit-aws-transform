"""
Abstract base server interface.
"""

import logging
import os
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI
from starlette_context import context as request_context
from strands.telemetry import StrandsTelemetry

from agent_builder_sdk.custom_types.common_types import (
    A2AError,
    A2AErrorCode,
    A2AMessage,
    InvocationRequest,
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
from agent_builder_sdk.messages.message_handler import MessageHandler
from agent_builder_sdk.notification.notification_handler import NotificationHandler
from agent_builder_sdk.server.server_models import AgentRuntimeContext
from agent_builder_sdk.task_handler import TaskHandler

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

        elif method == JsonRpcMethods.MESSAGE_SEND:
            # Method 4: A2A metadata (message/send)
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
            # Set context in class
            self.context = AgentRuntimeContext(
                workspace_id=init_request["workspaceId"],
                job_id=init_request["jobId"],
                agent_instance_id=init_request["agentInstanceId"],
                agent_id=init_request.get("agentId"),
                agent_version=init_request.get("agentVersion"),
                tenant_account_id=init_request.get("tenantAccountId"),
                initial_auth_token=init_request.get("authorizationToken"),
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

        @self.app.post("/invocations")
        async def handle_invocations(request: Dict[str, Any]) -> Dict[str, Any]:
            """Handle both AgentCore JSON-RPC and MDE notification requests."""
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
