import logging
from typing import Dict

from strands import Agent as StrandsAgent
from strands.agent import AgentResult as StrandsAgentResult

from agent_builder_sdk.orchestrator_strands.evaluation.evaluation_card import (
    EvaluationCard,
    EvaluationCategory,
    EvaluationOutput,
    EvaluationOutputDetail,
    EvaluationStatus,
)
from agent_builder_sdk.orchestrator_strands.evaluation.metrics_helper import MetricsHelper

logger = logging.getLogger(__name__)


class EvaluateAgent:
    def __init__(self, agent: StrandsAgent, eval_card: EvaluationCard):
        self.agent = agent
        self.eval_card = eval_card
        self.eval_iteration = 0
        self.eval_output: EvaluationOutput = EvaluationOutput()

    def evaluate(self, agent_result: StrandsAgentResult) -> EvaluationOutput:
        """
        Evaluate function of agent result based on its trajectories and metrics

        The following are the steps
          - Read eval card
          - Read agent metrics
          - Evaluate (see evaluation_card.py for details on these checks)
            - Output format
            - ToolUsage (needs to include required tools, optional tools need not be used, look for auth errors)
            - Task Efficiency Checks
            - Check if domain-level validation was performed
            - Task Manipulation Checks
            - HITL Usage Checks
            - Connector Usage Checks
            - Subagent Invocation Checks
          - Emit CW metrics w/agent metrics and eval results

        Args:
            agent_result(StrandsAgentResult): Result object from agent response

        Returns:
            EvaluationOutput

        """
        logger.info(f"Evaluating Agent: {self.eval_card.agent_name}")

        if agent_result.stop_reason != "end_turn":
            self.eval_output.task_completed = False
        else:
            logger.info("Verified that the agent task completed")

        # check if the output format matches
        # try:
        #     agent_output = self.agent.structured_output(self.eval_card.output_model, "Extract in the output format")
        #     self._update_eval_details(EvaluationCategory.OUTPUT_FORMAT, EvaluationStatus.SUCCESS, "")
        # except ValidationError as e:
        #     msg = f"Output format does not match the expected format: {e}"
        #     self._update_eval_details(EvaluationCategory.OUTPUT_FORMAT, EvaluationStatus.FAILED, msg)

        strands_metrics_summary = agent_result.metrics.get_summary()

        # tool usage check
        # - collect tool invocations from agent
        tool_use_map: Dict[str, int] = {}
        for index, message in enumerate(self.agent.messages):
            for content in message["content"]:
                if content.get("toolUse"):
                    tool_name = content["toolUse"]["name"]
                    tool_use_map[tool_name] = 1
        if self.eval_card.tool_usages:
            logger.info("Evaluating tool usages")
            for tool_usage in self.eval_card.tool_usages:
                tool_to_check = tool_usage.tool_name
                logger.info(f"Checking tool usage for {tool_to_check}")
                if tool_usage.is_required and tool_to_check not in tool_use_map:
                    msg = f"Tool {tool_to_check} is required but not used"
                    self._update_eval_details(
                        EvaluationCategory.TOOL_USAGE_CHECK, EvaluationStatus.FAILED, msg
                    )

        # task efficiency check
        if self.eval_card.task_efficiency_check.max_response_time_ms > 0:
            logger.info("Evaluating max response time")
            total_latency_ms = strands_metrics_summary.get("accumulated_metrics", {}).get(
                "latencyMs", 0
            )
            if total_latency_ms > self.eval_card.task_efficiency_check.max_response_time_ms:
                msg = f"Agent response time: {total_latency_ms} is longer than {self.eval_card.task_efficiency_check.max_response_time_ms}"
                self._update_eval_details(
                    EvaluationCategory.TASK_EFFICIENCY_CHECK, EvaluationStatus.FAILED, msg
                )

        if self.eval_card.task_efficiency_check.max_event_loop_cycles > 0:
            logger.info("Evaluating max agent event loop cycles")
            total_cycles = strands_metrics_summary.get("total_cycles", 0)
            if total_cycles > self.eval_card.task_efficiency_check.max_event_loop_cycles:
                msg = f"Agent ran more event loop cycles: {total_cycles} than the expected value of {self.eval_card.task_efficiency_check.max_event_loop_cycles}"
                self._update_eval_details(
                    EvaluationCategory.TASK_EFFICIENCY_CHECK, EvaluationStatus.FAILED, msg
                )

        if self.eval_card.task_efficiency_check.max_llm_token_usage > 0:
            logger.info("Evaluating total LLM cycles")
            total_tokens = strands_metrics_summary.get("accumulated_usage", {}).get(
                "inputTokens", 0
            )
            total_tokens += strands_metrics_summary.get("accumulated_usage", {}).get(
                "outputTokens", 0
            )
            if total_tokens > self.eval_card.task_efficiency_check.max_llm_token_usage:
                msg = f"Agent consumed more tokens: {total_tokens} than the expected value of {self.eval_card.task_efficiency_check.max_llm_token_usage}"
                self._update_eval_details(
                    EvaluationCategory.TASK_EFFICIENCY_CHECK, EvaluationStatus.FAILED, msg
                )

        # TODO:
        #  - domain validation check
        #  - task manipulation check
        #  - hitl usage check
        #  - connector usage check

        if self.eval_output.eval_status == EvaluationStatus.FAILED:
            logger.error("Overall Evaluation Status Failed")
            self.eval_output.agent_feedback_summary = "Evaluation of your response failed. Please try again with the following evaluation feedback -"
            self.eval_output.agent_feedback_summary += self.eval_output.eval_summary
            logger.error(f"Agent Feedback Summary: {self.eval_output.eval_summary}")

        # Emit Metrics
        MetricsHelper().emit_metrics(strands_metrics_summary, self.eval_output)

        return self.eval_output

    def _update_eval_details(
        self,
        eval_category: EvaluationCategory,
        eval_status: EvaluationStatus,
        eval_msg: str,
    ):
        """
        Updates the EvaluationDetail based on observation

        Args:
            eval_category (EvaluationCategory): What evaluation category does this observation correspond to
            eval_status (EvaluationStatus): Pass/Fail
            eval_msg (str): message to include
        """
        score_per_category: float = 100.0 / len(EvaluationCategory)
        self.eval_output.eval_details.append(
            EvaluationOutputDetail(category=eval_category, status=eval_status, msg=eval_msg)
        )
        if eval_msg:
            self.eval_output.eval_summary += eval_msg + "\n"
        if eval_status == EvaluationStatus.PASSED:
            self.eval_output.eval_score += score_per_category
            logger.info(
                f"Evaluation for category: {eval_category} succeeded. Eval score: {self.eval_output.eval_score}"
            )
        elif eval_status == EvaluationStatus.FAILED:
            self.eval_output.eval_status = EvaluationStatus.FAILED
            logger.info(f"Evaluation for category: {eval_category} failed.")
