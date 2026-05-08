# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""CloudWatch tools."""

import json
import os
import time
from typing import Any, Optional

import boto3
from mcp.server.fastmcp import FastMCP


def register_cloudwatch_tools(mcp: FastMCP) -> None:
    """Register CloudWatch tools with MCP server."""
    mcp.tool(description="Fetch log events from a CloudWatch log group")(fetch_logs)
    mcp.tool(description="List log streams in a CloudWatch log group")(list_log_streams)


def _get_cw_client() -> Any:
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("logs", region_name=region)


def _parse_relative_time(rel: str) -> int:
    """Parse relative time string like '15m', '1h', '2d' into milliseconds."""
    import re

    match = re.match(r"^(\d+)\s*(s|m|h|d)$", rel)
    if not match:
        raise ValueError(f'Invalid relativeTime format "{rel}". Use e.g. "15m", "1h", "2d".')
    value = int(match.group(1))
    unit = match.group(2)
    multipliers = {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return value * multipliers[unit]


def fetch_logs(
    log_group_name: str,
    filter_pattern: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    relative_time: Optional[str] = None,
    tail: bool = False,
    log_stream_names: Optional[list[str]] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
) -> str:
    """Fetch log events from a CloudWatch log group."""
    try:
        client = _get_cw_client()
        now = int(time.time() * 1000)
        resolved_start = start_time
        resolved_end = end_time

        if relative_time and resolved_start is None:
            offset = _parse_relative_time(relative_time)
            resolved_start = now - offset
            if resolved_end is None:
                resolved_end = now

        if tail and resolved_start is None:
            resolved_start = now - 3_600_000
            if resolved_end is None:
                resolved_end = now

        effective_limit = limit or 100

        kwargs: dict[str, Any] = {"logGroupName": log_group_name}
        if filter_pattern:
            kwargs["filterPattern"] = filter_pattern
        if resolved_start is not None:
            kwargs["startTime"] = resolved_start
        if resolved_end is not None:
            kwargs["endTime"] = resolved_end
        if log_stream_names:
            kwargs["logStreamNames"] = log_stream_names

        if tail:
            recent_events: list[Any] = []
            token = next_token
            for _ in range(10):
                call_kwargs = {**kwargs}
                if token:
                    call_kwargs["nextToken"] = token
                response = client.filter_log_events(**call_kwargs)
                recent_events.extend(response.get("events", []))
                if len(recent_events) > effective_limit:
                    recent_events = recent_events[-effective_limit:]
                token = response.get("nextToken")
                if not token:
                    break
            return json.dumps(
                {"events": recent_events, "resultCount": len(recent_events)},
                indent=2,
                default=str,
            )

        kwargs["limit"] = effective_limit
        if next_token:
            kwargs["nextToken"] = next_token
        response = client.filter_log_events(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_log_streams(
    log_group_name: str,
    order_by: str = "LastEventTime",
    descending: bool = True,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
) -> str:
    """List log streams in a CloudWatch log group."""
    try:
        client = _get_cw_client()
        kwargs: dict[str, Any] = {
            "logGroupName": log_group_name,
            "orderBy": order_by,
            "descending": descending,
        }
        if limit is not None:
            kwargs["limit"] = limit
        if next_token is not None:
            kwargs["nextToken"] = next_token
        response = client.describe_log_streams(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
