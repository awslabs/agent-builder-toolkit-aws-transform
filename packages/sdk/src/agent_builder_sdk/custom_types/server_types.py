# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Optional, Union

from pydantic import BaseModel


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[dict] = None
    id: Optional[Union[str, int]] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: Optional[Union[str, int]] = None


class JsonRpcError:
    PARSE_ERROR = {"code": -32700, "message": "Parse error"}
    INVALID_REQUEST = {"code": -32600, "message": "Invalid Request"}
    METHOD_NOT_FOUND = {"code": -32601, "message": "Method not found"}
    INVALID_PARAMS = {"code": -32602, "message": "Invalid params"}
    INTERNAL_ERROR = {"code": -32603, "message": "Internal error"}


class JsonRpcMethods:
    """JSON-RPC method constants using slash notation."""

    # ATX Agent endpoints
    INVOKE = "atx_agent/invoke"
    HEALTHCHECK = "atx_agent/healthcheck"
    HANDSHAKE = "atx_agent/handshake"
    NOTIFY = "atx_agent/notify"
    RESTORE = "atx_agent/restore"
    STOP = "atx_agent/stop"

    # A2A endpoints
    MESSAGE_SEND = "message/send"
    TASKS_GET = "tasks/get"
