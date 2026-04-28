"""Enhanced metrics helper with trace correlation using aws-embedded-metrics."""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from aws_embedded_metrics import metric_scope
from aws_embedded_metrics.logger.metrics_logger_factory import create_metrics_logger
from opentelemetry import trace

from agent_builder_sdk.env_var import (
    ENV_KEY_AGENT_INSTANCE_ID,
    ENV_KEY_AWS_REGION,
    ENV_KEY_JOB_ID,
    ENV_KEY_WORKSPACE_ID,
)

logger = logging.getLogger(__name__)


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
    ) -> Tuple[int, int, int, float]:
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

        # Calculate success rate if there were any calls
        success_rate = success_count / call_count if call_count > 0 else 0.0

        return call_count, error_count, success_count, success_rate

    def _emit_metrics_impl(self, metrics, strands_metrics_summary: Dict[str, Any]):
        """Internal implementation for emitting metrics."""
        trace_id = _get_current_trace_id()

        # Extract all metric values once
        accumulated_metrics = strands_metrics_summary.get("accumulated_metrics", {})
        accumulated_usage = strands_metrics_summary.get("accumulated_usage", {})

        latency_ms = accumulated_metrics.get("latencyMs", 0)
        input_tokens = accumulated_usage.get("inputTokens", 0)
        output_tokens = accumulated_usage.get("outputTokens", 0)
        total_cycles = strands_metrics_summary.get("total_cycles", 0)
        total_duration = strands_metrics_summary.get("total_duration", 0)

        # Extract tool usage metrics
        call_count, error_count, success_count, success_rate = self._extract_tool_usage_metrics(
            strands_metrics_summary
        )

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

        # Put metrics using extracted values
        metrics.put_metric("LatencyMs", latency_ms, "Milliseconds")
        metrics.put_metric("InputTokens", input_tokens, "Count")
        metrics.put_metric("OutputTokens", output_tokens, "Count")
        metrics.put_metric("ToolCallCount", call_count, "Count")
        metrics.put_metric("ErrorCount", error_count, "Count")
        metrics.put_metric("SuccessCount", success_count, "Count")
        metrics.put_metric("SuccessRate", success_rate, "None")
        metrics.put_metric("TotalCycles", total_cycles, "Count")
        metrics.put_metric("TotalDuration", total_duration, "Seconds")

        # Log metrics for visibility
        logger.info(
            f"Logging Agent metrics - Latency: {latency_ms}ms, InputTokens: {input_tokens}, "
            f"OutputTokens: {output_tokens}, ToolCalls: {call_count}, "
            f"SuccessRate: {success_rate:.2f}, Duration: {total_duration}s, TraceId: {trace_id}"
        )

        logger.info(f"Emitted metrics with EMF and trace correlation: {trace_id}")

    def emit_metrics(self, strands_metrics_summary: Dict[str, Any]):
        """Emit metrics - automatically handles both sync and async contexts."""
        try:
            # Check if we're in an async context
            loop = asyncio.get_running_loop()

            # We're in async context - schedule as background task
            async def async_emit():
                @metric_scope
                async def _async_impl(metrics):
                    self._emit_metrics_impl(metrics, strands_metrics_summary)

                await _async_impl()  # type: ignore[call-arg]

            loop.create_task(async_emit())  # type: ignore[call-arg]
            logger.info("Scheduled metrics emission in background")
        except RuntimeError:
            # No running loop - use sync approach
            metrics = create_metrics_logger()
            self._emit_metrics_impl(metrics, strands_metrics_summary)
