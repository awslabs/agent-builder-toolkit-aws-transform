"""Tests for evaluate_agent_trajectory module."""

from unittest.mock import Mock, patch

from agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory import (
    EvaluateAgent,
)
from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import (
    EvaluationCard,
    EvaluationCategory,
    EvaluationOutput,
    EvaluationStatus,
    TaskEfficiencyCheck,
    ToolUsage,
)


class TestEvaluateAgent:
    """Test EvaluateAgent class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_agent = Mock()
        self.eval_card = EvaluationCard(
            agent_name="Test Agent", agent_capabilities="Test capabilities"
        )
        self.evaluator = EvaluateAgent(self.mock_agent, self.eval_card)

    def test_init(self):
        """Test EvaluateAgent initialization."""
        assert self.evaluator.agent == self.mock_agent
        assert self.evaluator.eval_card == self.eval_card
        assert self.evaluator.eval_iteration == 0
        assert isinstance(self.evaluator.eval_output, EvaluationOutput)

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_task_completed(self, mock_metrics_helper):
        """Test evaluate method when task is completed."""
        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {
            "accumulated_metrics": {"latencyMs": 1000},
            "accumulated_usage": {"inputTokens": 100, "outputTokens": 50},
            "total_cycles": 5,
            "total_duration": 10.5,
        }

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.task_completed is True
        mock_metrics_helper.return_value.emit_metrics.assert_called_once()

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_task_not_completed(self, mock_metrics_helper):
        """Test evaluate method when task is not completed."""
        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "error"
        mock_agent_result.metrics.get_summary.return_value = {}

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.task_completed is False

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_tool_usage_required_tool_missing(self, mock_metrics_helper):
        """Test evaluation fails when required tool is not used."""
        self.eval_card.tool_usages = [
            ToolUsage("required_tool", True),
            ToolUsage("optional_tool", False),
        ]

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {}

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        assert len(result.eval_details) == 1
        assert result.eval_details[0].category == EvaluationCategory.TOOL_USAGE_CHECK
        assert result.eval_details[0].status == EvaluationStatus.FAILED
        assert "required_tool" in result.eval_details[0].msg

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_tool_usage_required_tool_present(self, mock_metrics_helper):
        """Test evaluation passes when required tool is used."""
        self.eval_card.tool_usages = [ToolUsage("required_tool", True)]

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {}

        self.mock_agent.messages = [{"content": [{"toolUse": {"name": "required_tool"}}]}]

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.PASSED

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_response_time_exceeded(self, mock_metrics_helper):
        """Test evaluation fails when response time exceeds limit."""
        self.eval_card.task_efficiency_check = TaskEfficiencyCheck(max_response_time_ms=1000)

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {
            "accumulated_metrics": {"latencyMs": 2000}
        }

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        assert any(
            detail.category == EvaluationCategory.TASK_EFFICIENCY_CHECK
            for detail in result.eval_details
        )

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_event_loop_cycles_exceeded(self, mock_metrics_helper):
        """Test evaluation fails when event loop cycles exceed limit."""
        self.eval_card.task_efficiency_check = TaskEfficiencyCheck(max_event_loop_cycles=10)

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {"total_cycles": 15}

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        assert any(
            detail.category == EvaluationCategory.TASK_EFFICIENCY_CHECK
            for detail in result.eval_details
        )

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_token_usage_exceeded(self, mock_metrics_helper):
        """Test evaluation fails when token usage exceeds limit."""
        self.eval_card.task_efficiency_check = TaskEfficiencyCheck(max_llm_token_usage=100)

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {
            "accumulated_usage": {"inputTokens": 80, "outputTokens": 50}
        }

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        assert any(
            detail.category == EvaluationCategory.TASK_EFFICIENCY_CHECK
            for detail in result.eval_details
        )

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_efficiency_checks_within_limits(self, mock_metrics_helper):
        """Test evaluation passes when all efficiency checks are within limits."""
        self.eval_card.task_efficiency_check = TaskEfficiencyCheck(
            max_response_time_ms=2000, max_event_loop_cycles=20, max_llm_token_usage=200
        )

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {
            "accumulated_metrics": {"latencyMs": 1000},
            "accumulated_usage": {"inputTokens": 80, "outputTokens": 50},
            "total_cycles": 10,
        }

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.PASSED

    def test_update_eval_details_passed(self):
        """Test _update_eval_details method with PASSED status."""
        initial_score = self.evaluator.eval_output.eval_score

        self.evaluator._update_eval_details(
            EvaluationCategory.OUTPUT_FORMAT_CHECK, EvaluationStatus.PASSED, "Test message"
        )

        assert len(self.evaluator.eval_output.eval_details) == 1
        detail = self.evaluator.eval_output.eval_details[0]
        assert detail.category == EvaluationCategory.OUTPUT_FORMAT_CHECK
        assert detail.status == EvaluationStatus.PASSED
        assert detail.msg == "Test message"
        assert "Test message" in self.evaluator.eval_output.eval_summary
        assert self.evaluator.eval_output.eval_score > initial_score

    def test_update_eval_details_failed(self):
        """Test _update_eval_details method with FAILED status."""
        self.evaluator._update_eval_details(
            EvaluationCategory.TOOL_USAGE_CHECK, EvaluationStatus.FAILED, "Tool check failed"
        )

        assert len(self.evaluator.eval_output.eval_details) == 1
        detail = self.evaluator.eval_output.eval_details[0]
        assert detail.category == EvaluationCategory.TOOL_USAGE_CHECK
        assert detail.status == EvaluationStatus.FAILED
        assert detail.msg == "Tool check failed"
        assert self.evaluator.eval_output.eval_status == EvaluationStatus.FAILED
        assert "Tool check failed" in self.evaluator.eval_output.eval_summary

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_failed_status_sets_feedback(self, mock_metrics_helper):
        """Test that failed evaluation sets agent feedback summary."""
        self.eval_card.tool_usages = [ToolUsage("missing_tool", True)]

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {}

        self.mock_agent.messages = []

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        assert "Evaluation of your response failed" in result.agent_feedback_summary
        assert result.eval_summary in result.agent_feedback_summary

    @patch(
        "agent_builder_sdk.orchestrator_strands.evaluation.evaluate_agent_trajectory.MetricsHelper"
    )
    def test_evaluate_complex_tool_usage_scenario(self, mock_metrics_helper):
        """Test complex tool usage scenario with multiple tools."""
        self.eval_card.tool_usages = [
            ToolUsage("tool1", True),
            ToolUsage("tool2", True),
            ToolUsage("tool3", False),
        ]

        mock_agent_result = Mock()
        mock_agent_result.stop_reason = "end_turn"
        mock_agent_result.metrics.get_summary.return_value = {}

        # Agent used tool1 and tool3, but not required tool2
        self.mock_agent.messages = [
            {"content": [{"toolUse": {"name": "tool1"}}]},
            {"content": [{"toolUse": {"name": "tool3"}}]},
            {"content": [{"text": "some text"}]},  # Non-tool content
        ]

        result = self.evaluator.evaluate(mock_agent_result)

        assert result.eval_status == EvaluationStatus.FAILED
        failed_details = [d for d in result.eval_details if d.status == EvaluationStatus.FAILED]
        assert len(failed_details) == 1
        assert "tool2" in failed_details[0].msg
