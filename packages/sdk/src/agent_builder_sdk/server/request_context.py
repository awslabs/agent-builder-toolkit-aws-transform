# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import uuid
from contextvars import ContextVar

from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send
from starlette_context.middleware import RawContextMiddleware
from structlog.contextvars import bound_contextvars
from typing_extensions import override

transaction_id: ContextVar[str | None] = ContextVar("transaction_id", default=None)


class RequestContextMiddleware(RawContextMiddleware):
    """Middleware that includes HTTP request information in the context."""

    @override
    async def set_context(self, request: HTTPConnection) -> dict:
        # Apply plugins, if any
        context = await super().set_context(request)

        http_request = context.setdefault("http", {}).setdefault("request", {})

        if method := request.scope.get("method"):
            http_request["method"] = method

        if status_code := request.scope.get("status"):
            http_request["status_code"] = status_code

        if id_ := request.headers.get("X-Request-ID", request.headers.get("X-Correlation-ID")):
            http_request["id"] = id_

        if address := request.client:
            client = context.setdefault("client", {})
            client["address"] = address.host
            client["port"] = address.port

        url = context.setdefault("url", {})
        url["full"] = str(request.url)

        if request.url.path:
            url["path"] = request.url.path

        return context

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        id_ = str(uuid.uuid4())
        token = transaction_id.set(id_)

        try:
            with bound_contextvars(**{"transaction.id": id_}):
                return await super().__call__(scope, receive, send)
        finally:
            transaction_id.reset(token)
