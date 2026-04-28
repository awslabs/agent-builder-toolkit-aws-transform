"""Tests for metrics_helper module."""

from unittest.mock import Mock, patch

from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import (
    EvaluationOutput,
    EvaluationStatus,
)
from agent_builder_sdk.orchestrator_strands.evaluation.metrics_helper import MetricsHelper


class TestMetricsHelper:
    """Test MetricsHelper class."""

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    def test_init(self):
        """Test MetricsHelper initialization."""
        helper = MetricsHelper()

        assert helper.workspace_id == "test-workspace"
        assert helper.job_id == "test-job"
        assert helper.agent_instance_id == "test-agent"
        assert helper.aws_region == "us-east-1"
        assert len(helper.dimensions_list) == 3

        assert helper.client.meta.service_model.service_name == "cloudwatch"
        assert helper.client.meta.region_name == "us-east-1"
        assert helper.client.meta.config.retries == {"mode": "standard"}

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_extract_metrics_basic(self, mock_boto_client):
        """Test _extract_metrics with basic metrics summary."""
        helper = MetricsHelper()

        strands_metrics = {
            "accumulated_metrics": {"latencyMs": 1500},
            "accumulated_usage": {"inputTokens": 100, "outputTokens": 50},
            "total_cycles": 5,
            "total_duration": 10.5,
            "tool_usage": {},
        }

        eval_output = EvaluationOutput(eval_status=EvaluationStatus.PASSED, eval_score=85.0)

        metrics = helper._extract_metrics(strands_metrics, eval_output)

        assert len(metrics) == 11

        # Check specific metrics
        latency_metric = next(m for m in metrics if m["MetricName"] == "LatencyMs")
        assert latency_metric["Value"] == 1500
        assert latency_metric["Unit"] == "Milliseconds"

        input_tokens_metric = next(m for m in metrics if m["MetricName"] == "InputTokens")
        assert input_tokens_metric["Value"] == 100

        eval_failure_metric = next(m for m in metrics if m["MetricName"] == "EvaluationFailure")
        assert eval_failure_metric["Value"] == 0

        eval_score_metric = next(m for m in metrics if m["MetricName"] == "EvaluationScore")
        assert eval_score_metric["Value"] == 85.0

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_extract_metrics_with_tool_usage(self, mock_boto_client):
        """Test _extract_metrics with tool usage data."""
        helper = MetricsHelper()

        strands_metrics = {
            "accumulated_metrics": {"latencyMs": 2000},
            "accumulated_usage": {"inputTokens": 200, "outputTokens": 100},
            "total_cycles": 8,
            "total_duration": 15.0,
            "tool_usage": {
                "tool1": {
                    "execution_stats": {"call_count": 3, "error_count": 1, "success_count": 2}
                },
                "tool2": {
                    "execution_stats": {"call_count": 2, "error_count": 0, "success_count": 2}
                },
            },
        }

        eval_output = EvaluationOutput(eval_status=EvaluationStatus.FAILED)

        metrics = helper._extract_metrics(strands_metrics, eval_output)

        tool_call_metric = next(m for m in metrics if m["MetricName"] == "ToolCallCount")
        assert tool_call_metric["Value"] == 5  # 3 + 2

        error_count_metric = next(m for m in metrics if m["MetricName"] == "ErrorCount")
        assert error_count_metric["Value"] == 1

        success_count_metric = next(m for m in metrics if m["MetricName"] == "SuccessCount")
        assert success_count_metric["Value"] == 4  # 2 + 2

        success_rate_metric = next(m for m in metrics if m["MetricName"] == "SuccessRate")
        assert success_rate_metric["Value"] == 0.8  # 4/5

        eval_failure_metric = next(m for m in metrics if m["MetricName"] == "EvaluationFailure")
        assert eval_failure_metric["Value"] == 1

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_extract_metrics_empty_data(self, mock_boto_client):
        """Test _extract_metrics with empty/missing data."""
        helper = MetricsHelper()

        strands_metrics = {}
        eval_output = EvaluationOutput()

        metrics = helper._extract_metrics(strands_metrics, eval_output)

        # Should still return all metrics with default values
        assert len(metrics) == 11

        latency_metric = next(m for m in metrics if m["MetricName"] == "LatencyMs")
        assert latency_metric["Value"] == 0

        success_rate_metric = next(m for m in metrics if m["MetricName"] == "SuccessRate")
        assert success_rate_metric["Value"] == 0.0

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_emit_metrics_success(self, mock_boto_client):
        """Test emit_metrics successful execution."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client

        helper = MetricsHelper()

        strands_metrics = {
            "accumulated_metrics": {"latencyMs": 1000},
            "accumulated_usage": {"inputTokens": 50, "outputTokens": 25},
            "total_cycles": 3,
            "total_duration": 5.0,
            "tool_usage": {},
        }

        eval_output = EvaluationOutput()

        helper.emit_metrics(strands_metrics, eval_output)

        mock_client.put_metric_data.assert_called_once()
        call_args = mock_client.put_metric_data.call_args[1]

        assert call_args["Namespace"] == "StrandsAgentMetrics"
        assert "MetricData" in call_args
        assert len(call_args["MetricData"]) == 11

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_emit_metrics_exception(self, mock_boto_client):
        """Test emit_metrics handles exceptions."""
        mock_client = Mock()
        mock_client.put_metric_data.side_effect = Exception("CloudWatch error")
        mock_boto_client.return_value = mock_client

        helper = MetricsHelper()

        strands_metrics = {}
        eval_output = EvaluationOutput()

        # Should not raise exception
        helper.emit_metrics(strands_metrics, eval_output)

        mock_client.put_metric_data.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_dimensions_list_format(self, mock_boto_client):
        """Test dimensions list is properly formatted."""
        helper = MetricsHelper()

        expected_dimensions = [
            {"Name": "workspaceId", "Value": "test-workspace"},
            {"Name": "jobId", "Value": "test-job"},
            {"Name": "agentInstanceId", "Value": "test-agent"},
        ]

        assert helper.dimensions_list == expected_dimensions

    @patch.dict(
        "os.environ",
        {
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
            "AWS_REGION": "us-east-1",
        },
    )
    @patch("boto3.client")
    def test_tool_usage_zero_calls(self, mock_boto_client):
        """Test tool usage metrics when no tools are called."""
        helper = MetricsHelper()

        strands_metrics = {
            "tool_usage": {
                "tool1": {
                    "execution_stats": {"call_count": 0, "error_count": 0, "success_count": 0}
                }
            }
        }

        eval_output = EvaluationOutput()

        metrics = helper._extract_metrics(strands_metrics, eval_output)

        success_rate_metric = next(m for m in metrics if m["MetricName"] == "SuccessRate")
        assert success_rate_metric["Value"] == 0.0
