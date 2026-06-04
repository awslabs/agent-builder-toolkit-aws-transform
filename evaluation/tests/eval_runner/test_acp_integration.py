# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the eval_runner ↔ ACP execution-engine integration.

Covers the bridge between eval_runner's canonical models and the ACP execution
engine (:mod:`eval_runner.execution`): ``TestCase.to_scenario()``, the
``ACPAgent`` execution backend, and the ``llm_judge`` metric. The orchestrator is
mocked throughout so these tests need no model access or ACP driver.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from eval_runner.models import (
    AssertionResult,
    AssertionResultStatus,
    EvalResult,
    ExecutionResult,
    TranscriptEntry,
    TranscriptRole,
)
from eval_runner.test_case import TestCase


class TestToScenario:
    def test_maps_fields_onto_eval_case(self) -> None:
        tc = TestCase(
            id="t1",
            name="My test",
            user_message="do the thing",
            description="goal",
            tags=["x"],
            max_turns=4,
            timeout_seconds=120,
            simulated_human_guidance="be terse",
            assertions=[{"name": "a", "type": "llm_judge"}],
        )
        scenario = tc.to_scenario()

        assert scenario.id == "t1"
        assert scenario.name == "My test"
        assert scenario.prompt == "do the thing"  # user_message -> prompt
        assert scenario.description == "goal"
        assert scenario.tags == ["x"]
        assert scenario.max_turns == 4
        assert scenario.timeout_seconds == 120
        assert scenario.simulated_human_guidance == "be terse"
        assert scenario.assertions == [{"name": "a", "type": "llm_judge"}]


def _eval_result_with_tools() -> EvalResult:
    return EvalResult(
        eval_id="t1",
        transcript=[
            TranscriptEntry(role=TranscriptRole.HUMAN, content="hello", turn=1),
            TranscriptEntry(
                role=TranscriptRole.TOOL_CALL,
                content="tool_call: get_status (kind=mcp, status=ok)",
                turn=1,
            ),
            TranscriptEntry(role=TranscriptRole.AGENT, content="all good", turn=1),
        ],
        turn_count=1,
        duration_seconds=2.5,
    )


class TestACPAgent:
    def test_execute_flattens_transcript(self) -> None:
        from eval_runner.agents.acp_agent import ACPAgent

        orchestrator = MagicMock()
        orchestrator.run_scenario.return_value = _eval_result_with_tools()

        agent = ACPAgent(execution_config=MagicMock(), orchestrator=orchestrator)
        tc = TestCase(id="t1", name="T", user_message="hello")

        execution = agent.execute(tc)

        assert isinstance(execution, ExecutionResult)
        # Output is the agent's last message.
        assert execution.output == "all good"
        # Transcript string contains all turns.
        assert "hello" in execution.transcript
        assert "all good" in execution.transcript
        # Tool call extracted and keyed for deterministic metrics.
        assert execution.tool_calls == [
            {"name": "get_status", "tool": "get_status", "turn": 1}
        ]
        assert execution.duration_ms == 2500
        # run_scenario was called with the converted scenario.
        called_scenario = orchestrator.run_scenario.call_args.args[0]
        assert called_scenario.id == "t1"

    def test_execute_satisfies_eval_agent_interface(self) -> None:
        from eval_runner.agent_interface import EvalAgentInterface
        from eval_runner.agents.acp_agent import ACPAgent

        agent = ACPAgent(execution_config=MagicMock(), orchestrator=MagicMock())
        assert isinstance(agent, EvalAgentInterface)


class TestLLMJudgeMetric:
    def test_requires_config_or_orchestrator(self) -> None:
        from eval_runner.metrics.llm_judge import LLMJudgeMetric

        with pytest.raises(ValueError):
            LLMJudgeMetric()

    def test_no_assertions_passes(self) -> None:
        from eval_runner.metrics.llm_judge import LLMJudgeMetric

        metric = LLMJudgeMetric(orchestrator=MagicMock())
        tc = TestCase(id="t1", name="T", user_message="hi", assertions=[])
        execution = ExecutionResult(transcript="x", output="y")

        result = metric.evaluate(execution, tc)
        assert result.passed is True
        assert result.score == 10.0

    def test_scores_from_judge_verdicts(self) -> None:
        from eval_runner.metrics.llm_judge import LLMJudgeMetric

        orchestrator = MagicMock()
        orchestrator.grade_transcript.return_value = (
            [
                AssertionResult(name="a", result=AssertionResultStatus.PASS, evidence="ok"),
                AssertionResult(name="b", result=AssertionResultStatus.FAIL, evidence="no"),
            ],
            "/tmp/judge.log",
            "sess-1",
        )

        metric = LLMJudgeMetric(orchestrator=orchestrator)
        tc = TestCase(
            id="t1",
            name="T",
            user_message="hi",
            assertions=[{"name": "a"}, {"name": "b"}],
        )
        execution = ExecutionResult(transcript="[Turn 1] AGENT: hi", output="hi")

        result = metric.evaluate(execution, tc)

        # 1 of 2 passed -> 5.0, below the 7.0 threshold.
        assert result.score == 5.0
        assert result.passed is False
        assert len(result.details["assertions"]) == 2
        # Judge graded the flattened transcript string (no re-run).
        assert orchestrator.grade_transcript.call_args.args[0] == "[Turn 1] AGENT: hi"


class TestEngineWiresLLMJudge:
    def test_from_config_binds_llm_judge_with_execution_config(self) -> None:
        from eval_runner.config import EvalConfig
        from eval_runner.engine import EvaluationEngine

        config = EvalConfig(
            metrics=["assertion_pass_rate", "llm_judge"],
            execution_config=MagicMock(),
        )
        engine = EvaluationEngine.from_config(config)
        names = {m.name for m in engine.metrics}
        assert names == {"assertion_pass_rate", "llm_judge"}
