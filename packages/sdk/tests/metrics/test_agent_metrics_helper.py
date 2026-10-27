# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for MetricsHelper."""

import asyncio
import importlib
import os
from unittest import mock

import pytest
from aws_embedded_metrics.config import get_config

from agent_builder_sdk.metrics import metrics_helper
from agent_builder_sdk.metrics.metrics_helper import MetricsHelper, _get_current_trace_id


class TestMetricsHelper:
    """Test cases for MetricsHelper."""

    @pytest.fixture
    def env_vars(self):
        """Environment variables for testing."""
        return {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        }

    def test_init_default(self, env_vars):
        """Test MetricsHelper initialization with defaults."""
        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper()

            assert helper.namespace == "StrandsAgentMetrics"
            assert helper.workspace_id == "test-workspace"
            assert helper.job_id == "test-job"
            assert helper.agent_instance_id == "test-agent"
            assert helper.aws_region == "us-east-1"
            assert helper.custom_dimensions == {}

    def test_init_custom_namespace_and_dimensions(self, env_vars):
        """Test MetricsHelper initialization with custom values."""
        custom_dims = {"env": "test", "version": "1.0"}

        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper(custom_dimensions=custom_dims, namespace="CustomNamespace")

            assert helper.namespace == "CustomNamespace"
            assert helper.custom_dimensions == custom_dims

    def test_init_missing_env_vars(self):
        """Test MetricsHelper initialization with missing environment variables."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Should not raise an error
            helper = MetricsHelper()
            assert helper.workspace_id is None
            assert helper.job_id is None
            assert helper.agent_instance_id is None

    @mock.patch("agent_builder_sdk.metrics.metrics_helper._get_current_trace_id")
    def test_emit_metrics_success(self, mock_trace_id, env_vars):
        """Test successful metrics emission."""
        mock_trace_id.return_value = "abc123"

        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper()
            metrics_summary = {
                "accumulated_metrics": {"latencyMs": 100},
                "accumulated_usage": {"inputTokens": 50, "outputTokens": 25},
                "tool_usage": {
                    "tool1": {
                        "execution_stats": {"call_count": 5, "error_count": 1, "success_count": 4}
                    }
                },
                "total_cycles": 1,
                "total_duration": 2.5,
            }

            # Mock the metrics object that gets passed to the decorated function
            mock_metrics = mock.Mock()

            # Call the underlying function directly (bypassing decorator for testing)
            helper._emit_metrics_impl(mock_metrics, helper._totals(metrics_summary))

            # Verify metrics calls
            mock_metrics.set_namespace.assert_called_once_with("StrandsAgentMetrics")
            mock_metrics.set_property.assert_any_call("workspaceId", "test-workspace")
            mock_metrics.set_property.assert_any_call("jobId", "test-job")
            mock_metrics.set_property.assert_any_call("agentInstanceId", "test-agent")
            mock_metrics.set_property.assert_any_call("traceId", "abc123")

            # Verify put_metric calls
            mock_metrics.put_metric.assert_any_call("LatencyMs", 100, "Milliseconds")
            mock_metrics.put_metric.assert_any_call("InputTokens", 50, "Count")
            mock_metrics.put_metric.assert_any_call("OutputTokens", 25, "Count")
            mock_metrics.put_metric.assert_any_call("ErrorCount", 1, "Count")
            mock_metrics.put_metric.assert_any_call("SuccessRate", 0.8, "None")

    @mock.patch("agent_builder_sdk.metrics.metrics_helper._get_current_trace_id")
    def test_emit_metrics_with_custom_dimensions(self, mock_trace_id, env_vars):
        """Test metrics emission with custom dimensions."""
        mock_trace_id.return_value = None
        custom_dims = {"env": "test", "version": "1.0"}

        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper(custom_dimensions=custom_dims)
            metrics_summary = {"accumulated_metrics": {}}

            mock_metrics = mock.Mock()
            helper._emit_metrics_impl(mock_metrics, helper._totals(metrics_summary))

            # Verify custom dimensions are set
            mock_metrics.set_dimensions.assert_called_once_with(**custom_dims)

    def test_emit_metrics_reports_the_turn_since_the_baseline(self, env_vars):
        first_turn = {
            "accumulated_metrics": {"latencyMs": 100},
            "accumulated_usage": {
                "inputTokens": 5,
                "outputTokens": 20,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": 900,
            },
            "tool_usage": {
                "tool1": {
                    "execution_stats": {"call_count": 2, "error_count": 2, "success_count": 0}
                }
            },
            "total_cycles": 3,
            "total_duration": 4.0,
        }
        after_second_turn = {
            "accumulated_metrics": {"latencyMs": 250},
            "accumulated_usage": {
                "inputTokens": 8,
                "outputTokens": 50,
                "cacheReadInputTokens": 1800,
                "cacheWriteInputTokens": 1000,
            },
            "tool_usage": first_turn["tool_usage"],
            "total_cycles": 4,
            "total_duration": 5.5,
        }
        loggers = [mock.Mock(), mock.Mock()]

        with mock.patch.dict(os.environ, env_vars), mock.patch(
            "agent_builder_sdk.metrics.metrics_helper.create_metrics_logger",
            side_effect=loggers,
        ):
            helper = MetricsHelper()
            totals = helper.emit_metrics(after_second_turn, helper.emit_metrics(first_turn))

        assert totals == helper._totals(after_second_turn)

        def emitted(metrics_logger):
            return {c.args[0]: c.args[1] for c in metrics_logger.put_metric.call_args_list}

        assert emitted(loggers[0])["CacheWriteInputTokens"] == 900
        assert emitted(loggers[0])["SuccessRate"] == 0.0
        # The second turn made no tool calls, so it has no success rate.
        assert emitted(loggers[1]) == {
            "LatencyMs": 150,
            "InputTokens": 3,
            "OutputTokens": 30,
            "CacheReadInputTokens": 1800,
            "CacheWriteInputTokens": 100,
            "ToolCallCount": 0,
            "ErrorCount": 0,
            "SuccessCount": 0,
            "TotalCycles": 1,
            "TotalDuration": 1.5,
        }

    async def test_emit_metrics_in_a_running_loop_reports_the_turn(self, env_vars):
        first = {"accumulated_usage": {"inputTokens": 5}, "total_cycles": 3}
        second = {"accumulated_usage": {"inputTokens": 8}, "total_cycles": 4}

        with mock.patch.dict(os.environ, env_vars), mock.patch.object(
            MetricsHelper, "_emit_metrics_impl"
        ) as emit_impl, mock.patch(
            "aws_embedded_metrics.metric_scope.create_metrics_logger",
            return_value=mock.AsyncMock(),
        ):
            helper = MetricsHelper()
            helper.emit_metrics(second, helper.emit_metrics(first))
            await asyncio.sleep(0)

        assert [c.args[1]["InputTokens"] for c in emit_impl.call_args_list] == [5, 3]

    def test_extract_tool_usage_metrics_basic(self, env_vars):
        """Test basic tool usage metrics extraction."""
        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper()
            metrics_summary = {
                "tool_usage": {
                    "tool1": {
                        "execution_stats": {"call_count": 3, "error_count": 1, "success_count": 2}
                    },
                    "tool2": {
                        "execution_stats": {"call_count": 2, "error_count": 0, "success_count": 2}
                    },
                }
            }

            call_count, error_count, success_count = helper._extract_tool_usage_metrics(
                metrics_summary
            )

            assert call_count == 5  # 3 + 2
            assert error_count == 1  # 1 + 0
            assert success_count == 4  # 2 + 2

    def test_extract_tool_usage_metrics_empty(self, env_vars):
        """Test tool usage metrics extraction with no tools."""
        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper()
            metrics_summary = {"tool_usage": {}}

            call_count, error_count, success_count = helper._extract_tool_usage_metrics(
                metrics_summary
            )

            assert call_count == 0
            assert error_count == 0
            assert success_count == 0


class TestGetCurrentTraceId:
    """Test cases for _get_current_trace_id function."""

    @mock.patch("opentelemetry.trace.get_current_span")
    def test_get_trace_id_success(self, mock_get_span):
        """Test successful trace ID extraction."""
        mock_span = mock.Mock()
        mock_context = mock.Mock()
        mock_context.trace_id = 12345
        mock_span.get_span_context.return_value = mock_context
        mock_get_span.return_value = mock_span

        trace_id = _get_current_trace_id()

        assert trace_id == "3039"  # hex of 12345

    @mock.patch("opentelemetry.trace.get_current_span")
    def test_get_trace_id_no_span(self, mock_get_span):
        """Test trace ID extraction with no active span."""
        mock_get_span.return_value = None

        trace_id = _get_current_trace_id()

        assert trace_id is None

    @mock.patch("opentelemetry.trace.get_current_span")
    def test_get_trace_id_exception(self, mock_get_span):
        """Test trace ID extraction with exception."""
        mock_get_span.side_effect = Exception("Tracing error")

        trace_id = _get_current_trace_id()

        assert trace_id is None


class TestEmfEnvironmentDefault:
    """On AgentCore EMF writes to stdout unless AWS_EMF_ENVIRONMENT says otherwise; elsewhere EMF
    keeps its own environment detection."""

    @pytest.fixture(autouse=True)
    def restore_config(self):
        saved = get_config().environment
        yield
        get_config().environment = saved

    @staticmethod
    def _reload(env):
        get_config().environment = env.get("AWS_EMF_ENVIRONMENT")
        with mock.patch.dict(os.environ, env, clear=False):
            for key in ("AWS_EMF_ENVIRONMENT", "AWS_EXECUTION_ENV"):
                if key not in env:
                    os.environ.pop(key, None)
            importlib.reload(metrics_helper)
        return get_config().environment

    def test_defaults_to_local_on_agentcore(self):
        assert self._reload({"AWS_EXECUTION_ENV": "AWS_BedrockAgentCore_Runtime"}) == "local"

    def test_leaves_detection_alone_off_agentcore(self):
        assert self._reload({}) is None
        assert self._reload({"AWS_EXECUTION_ENV": "AWS_Lambda_python3.12"}) is None

    def test_keeps_explicit_environment_on_agentcore(self):
        env = {"AWS_EXECUTION_ENV": "AWS_BedrockAgentCore_Runtime", "AWS_EMF_ENVIRONMENT": "ec2"}
        assert self._reload(env) == "ec2"
