# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Enhanced metrics helper with trace correlation using aws-embedded-metrics."""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from aws_embedded_metrics import metric_scope
from aws_embedded_metrics.config import get_config
from aws_embedded_metrics.logger.metrics_logger_factory import create_metrics_logger
from opentelemetry import trace

from agent_builder_sdk.env_var import (
    ENV_KEY_AGENT_INSTANCE_ID,
    ENV_KEY_AWS_REGION,
    ENV_KEY_JOB_ID,
    ENV_KEY_WORKSPACE_ID,
)

logger = logging.getLogger(__name__)

# AgentCore answers the EC2 metadata probe without an imageId, so EMF's EC2 detection fails.
# Write records to stdout, which AgentCore ships to CloudWatch Logs. AWS_EMF_ENVIRONMENT wins.
if not os.environ.get("AWS_EMF_ENVIRONMENT"):
    get_config().environment = "local"

_UNITS = {
    "LatencyMs": "Milliseconds",
    "InputTokens": "Count",
    "OutputTokens": "Count",
    "CacheReadInputTokens": "Count",
    "CacheWriteInputTokens": "Count",
    "ToolCallCount": "Count",
    "ErrorCount": "Count",
    "SuccessCount": "Count",
    "TotalCycles": "Count",
    "TotalDuration": "Seconds",
}


def _get_current_trace_id() -> Optional[str]:
    """Get current trace ID for metrics correlation."""
    try:
        span = trace.get_current_span()
        if span and span.get_span_context().trace_id:
            # Format as hexadecimal string ('x' = lowercase hex without 0x prefix)
            return format(span.get_span_context().trace_id, "x")
    except Exception:
        pass  # Ignore any tracing errors
    return None


class MetricsHelper:
    """Metrics helper with automatic trace correlation using aws-embedded-metrics."""

    def __init__(
        self,
        custom_dimensions: Optional[Dict[str, str]] = None,
        namespace: str = "StrandsAgentMetrics",
    ):
        self.workspace_id = os.getenv(ENV_KEY_WORKSPACE_ID)
        self.job_id = os.getenv(ENV_KEY_JOB_ID)
        self.agent_instance_id = os.getenv(ENV_KEY_AGENT_INSTANCE_ID)
        self.aws_region = os.getenv(ENV_KEY_AWS_REGION)
        self.namespace = namespace
        self.custom_dimensions = custom_dimensions or {}

        logger.info("Initialized MetricsHelper with aws-embedded-metrics")

    def _extract_tool_usage_metrics(
        self, strands_metrics_summary: Dict[str, Any]
    ) -> Tuple[int, int, int]:
        """Extract and aggregate tool usage metrics."""
        tool_usage = strands_metrics_summary.get("tool_usage", {})
        call_count = 0
        error_count = 0
        success_count = 0

        # Aggregate metrics across all tools
        for tool_name, tool_data in tool_usage.items():
            execution_stats = tool_data.get("execution_stats", {})
            call_count += execution_stats.get("call_count", 0)
            error_count += execution_stats.get("error_count", 0)
            success_count += execution_stats.get("success_count", 0)

        return call_count, error_count, success_count

    def _totals(self, strands_metrics_summary: Dict[str, Any]) -> Dict[str, float]:
        usage = strands_metrics_summary.get("accumulated_usage", {})
        call_count, error_count, success_count = self._extract_tool_usage_metrics(
            strands_metrics_summary
        )
        return {
            "LatencyMs": strands_metrics_summary.get("accumulated_metrics", {}).get("latencyMs", 0),
            "InputTokens": usage.get("inputTokens", 0),
            "OutputTokens": usage.get("outputTokens", 0),
            "CacheReadInputTokens": usage.get("cacheReadInputTokens", 0),
            "CacheWriteInputTokens": usage.get("cacheWriteInputTokens", 0),
            "ToolCallCount": call_count,
            "ErrorCount": error_count,
            "SuccessCount": success_count,
            "TotalCycles": strands_metrics_summary.get("total_cycles", 0),
            "TotalDuration": strands_metrics_summary.get("total_duration", 0),
        }

    def _emit_metrics_impl(self, metrics, values: Dict[str, float]):
        """Internal implementation for emitting metrics."""
        trace_id = _get_current_trace_id()

        call_count = values["ToolCallCount"]
        success_rate = values["SuccessCount"] / call_count if call_count else None

        # Set namespace
        metrics.set_namespace(self.namespace)

        # Set custom dimensions only (if any)
        if self.custom_dimensions:
            metrics.set_dimensions(**self.custom_dimensions)

        # Set all as properties (no cardinality impact)
        if self.workspace_id:
            metrics.set_property("workspaceId", self.workspace_id)
        if self.job_id:
            metrics.set_property("jobId", self.job_id)
        if self.agent_instance_id:
            metrics.set_property("agentInstanceId", self.agent_instance_id)
        if trace_id:
            metrics.set_property("traceId", trace_id)

        for name, unit in _UNITS.items():
            metrics.put_metric(name, values[name], unit)
        # A record without tool calls has no success rate; a 0 here would drag the average down.
        if success_rate is not None:
            metrics.put_metric("SuccessRate", success_rate, "None")

        # Log metrics for visibility
        logger.info(
            f"Logging Agent metrics - Latency: {values['LatencyMs']}ms, "
            f"InputTokens: {values['InputTokens']}, OutputTokens: {values['OutputTokens']}, "
            f"ToolCalls: {call_count}, "
            f"SuccessRate: {'n/a' if success_rate is None else round(success_rate, 2)}, "
            f"Duration: {values['TotalDuration']}s, "
            f"CacheReadInputTokens: {values['CacheReadInputTokens']}, "
            f"CacheWriteInputTokens: {values['CacheWriteInputTokens']}, TraceId: {trace_id}"
        )

        logger.info(f"Emitted metrics with EMF and trace correlation: {trace_id}")

    def emit_metrics(
        self,
        strands_metrics_summary: Dict[str, Any],
        baseline: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Emit the change in the summary's counters since ``baseline``; return the new totals.

        A Strands summary counts from the agent's creation, not per invocation, so an agent that
        serves many turns passes the totals this returned last time to emit one turn per record.
        Without a baseline the whole summary is emitted. Inside a running loop the record goes out
        from a background task after this returns, so a record lost there takes its turn with it.
        """
        totals = self._totals(strands_metrics_summary)
        previous = baseline or {}
        values = {name: total - previous.get(name, 0) for name, total in totals.items()}
        try:
            # Check if we're in an async context
            loop = asyncio.get_running_loop()

            # We're in async context - schedule as background task
            async def async_emit():
                @metric_scope
                async def _async_impl(metrics):
                    self._emit_metrics_impl(metrics, values)

                await _async_impl()  # type: ignore[call-arg]

            loop.create_task(async_emit())  # type: ignore[call-arg]
            logger.info("Scheduled metrics emission in background")
        except RuntimeError:
            # No running loop - use sync approach
            metrics = create_metrics_logger()
            self._emit_metrics_impl(metrics, values)
        return totals
