# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for MetricsHelper."""

import os
from unittest import mock

import pytest

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
                "tool_usage": {},
                "total_cycles": 1,
                "total_duration": 2.5,
            }

            # Mock the metrics object that gets passed to the decorated function
            mock_metrics = mock.Mock()

            # Call the underlying function directly (bypassing decorator for testing)
            helper._emit_metrics_impl(mock_metrics, metrics_summary)

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

    @mock.patch("agent_builder_sdk.metrics.metrics_helper._get_current_trace_id")
    def test_emit_metrics_with_custom_dimensions(self, mock_trace_id, env_vars):
        """Test metrics emission with custom dimensions."""
        mock_trace_id.return_value = None
        custom_dims = {"env": "test", "version": "1.0"}

        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper(custom_dimensions=custom_dims)
            metrics_summary = {"accumulated_metrics": {}}

            mock_metrics = mock.Mock()
            helper._emit_metrics_impl(mock_metrics, metrics_summary)

            # Verify custom dimensions are set
            mock_metrics.set_dimensions.assert_called_once_with(**custom_dims)

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

            call_count, error_count, success_count, success_rate = (
                helper._extract_tool_usage_metrics(metrics_summary)
            )

            assert call_count == 5  # 3 + 2
            assert error_count == 1  # 1 + 0
            assert success_count == 4  # 2 + 2
            assert success_rate == 0.8  # 4/5

    def test_extract_tool_usage_metrics_empty(self, env_vars):
        """Test tool usage metrics extraction with no tools."""
        with mock.patch.dict(os.environ, env_vars):
            helper = MetricsHelper()
            metrics_summary = {"tool_usage": {}}

            call_count, error_count, success_count, success_rate = (
                helper._extract_tool_usage_metrics(metrics_summary)
            )

            assert call_count == 0
            assert error_count == 0
            assert success_count == 0
            assert success_rate == 0.0


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
