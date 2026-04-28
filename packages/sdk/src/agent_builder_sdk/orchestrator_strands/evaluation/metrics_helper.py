import logging
import os

import boto3
from botocore.config import Config as BotoConfig

from agent_builder_sdk.env_var import (
    ENV_KEY_AGENT_INSTANCE_ID,
    ENV_KEY_AWS_REGION,
    ENV_KEY_JOB_ID,
    ENV_KEY_WORKSPACE_ID,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import (
    EvaluationOutput,
    EvaluationStatus,
)

logger = logging.getLogger(__name__)


class MetricsHelper:
    def __init__(self):
        self.workspace_id = os.getenv(ENV_KEY_WORKSPACE_ID)
        self.job_id = os.getenv(ENV_KEY_JOB_ID)
        self.agent_instance_id = os.getenv(ENV_KEY_AGENT_INSTANCE_ID)
        self.aws_region = os.getenv(ENV_KEY_AWS_REGION)
        logger.info("Creating CloudWatch Metrics client..")
        default_dimensions = {
            "workspaceId": self.workspace_id,
            "jobId": self.job_id,
            "agentInstanceId": self.agent_instance_id,
        }
        self.dimensions_list = [{"Name": k, "Value": v} for k, v in default_dimensions.items()]
        self.client = boto3.client(
            service_name="cloudwatch",
            region_name=self.aws_region,
            config=BotoConfig(retries={"mode": "standard"}),
        )

    def _extract_metrics(self, strands_metrics_summary, eval_output: EvaluationOutput):
        """
        Extract key metrics from the agent's metrics summary and format them as EMF.

        Args:
            strands_metrics_summary (dict): The metrics summary from agent.metrics.get_summary()
            eval_output (EvaluationOutput): Output of agent evaluation after execution

        Returns:
            dict: EMF-formatted metrics
        """
        # Extract tool usage metrics
        tool_usage = strands_metrics_summary.get("tool_usage", {})
        call_count = 0
        error_count = 0
        success_count = 0
        success_rate: float = 0.0

        # Aggregate metrics across all tools
        for tool_name, tool_data in tool_usage.items():
            execution_stats = tool_data.get("execution_stats", {})
            call_count += execution_stats.get("call_count", 0)
            error_count += execution_stats.get("error_count", 0)
            success_count += execution_stats.get("success_count", 0)

        # Calculate success rate if there were any calls
        if call_count > 0:
            success_rate = success_count / call_count

        # Form the metrics array
        cf_metrics_data = [
            {
                "MetricName": "LatencyMs",
                "Unit": "Milliseconds",
                "Value": strands_metrics_summary.get("accumulated_metrics", {}).get("latencyMs", 0),
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "InputTokens",
                "Unit": "Count",
                "Value": strands_metrics_summary.get("accumulated_usage", {}).get("inputTokens", 0),
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "OutputTokens",
                "Unit": "Count",
                "Value": strands_metrics_summary.get("accumulated_usage", {}).get(
                    "outputTokens", 0
                ),
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "ToolCallCount",
                "Unit": "Count",
                "Value": call_count,
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "ErrorCount",
                "Unit": "Count",
                "Value": error_count,
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "SuccessCount",
                "Unit": "Count",
                "Value": success_count,
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "SuccessRate",
                "Unit": "None",
                "Value": success_rate,
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "TotalCycles",
                "Unit": "Count",
                "Value": strands_metrics_summary.get("total_cycles", 0),
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "TotalDuration",
                "Unit": "Seconds",
                "Value": strands_metrics_summary.get("total_duration", 0),
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "EvaluationFailure",
                "Unit": "Count",
                "Value": 1 if eval_output.eval_status == EvaluationStatus.FAILED else 0,
                "Dimensions": self.dimensions_list,
            },
            {
                "MetricName": "EvaluationScore",
                "Unit": "Count",
                "Value": eval_output.eval_score,
                "Dimensions": self.dimensions_list,
            },
        ]

        return cf_metrics_data

    def emit_metrics(self, strands_metrics_summary, eval_output: EvaluationOutput):
        """
        Save the extracted metrics to a file in EMF format.

        Args:
            strands_metrics_summary (dict): The metrics summary from agent.metrics.get_summary()
            eval_output (EvaluationOutput): Output of agent evaluation after execution

        """
        input_request = dict(
            Namespace="StrandsAgentMetrics",
            MetricData=self._extract_metrics(strands_metrics_summary, eval_output),
        )
        try:
            self.client.put_metric_data(**input_request)
            logger.info("successfully put metric data")
        except Exception as e:
            logger.error(f"error while putting metric data, exception: {str(e)}")
