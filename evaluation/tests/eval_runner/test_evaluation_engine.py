# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for EvaluationEngine (task 1.4)."""

import json

from eval_runner.config import EvalConfig
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase


class FakeAgent:
    """Test agent that echoes user_message."""

    def execute(self, test_case: TestCase) -> ExecutionResult:
        return ExecutionResult(
            transcript=f"User: {test_case.user_message}\nAgent: Done.",
            output=f"Processed: {test_case.user_message}",
            tool_calls=[{"name": "search", "input": {"q": "test"}}],
            duration_ms=150,
        )


class FailingAgent:
    """Agent that always raises."""

    def execute(self, test_case: TestCase) -> ExecutionResult:
        raise RuntimeError("Agent crashed")


class AlwaysPassMetric:
    """Metric that always passes with score 9.0."""

    @property
    def name(self) -> str:
        return "always_pass"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        return MetricResult(metric_name=self.name, score=9.0, passed=True)


class AlwaysFailMetric:
    """Metric that always fails with score 2.0."""

    @property
    def name(self) -> str:
        return "always_fail"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        return MetricResult(metric_name=self.name, score=2.0, passed=False)


class TestEvaluationEngine:
    def _make_test_cases(self, count: int = 3) -> list[TestCase]:
        return [
            TestCase(id=f"tc-{i}", name=f"Test {i}", user_message=f"message {i}")
            for i in range(count)
        ]

    def test_evaluate_single_test_case(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FakeAgent()
        tc = TestCase(id="tc-1", name="Test 1", user_message="hello")

        result = engine.evaluate(agent, tc)
        assert result.test_case_id == "tc-1"
        assert result.execution.output == "Processed: hello"
        assert result.passed is True
        assert len(result.metric_results) == 1
        assert result.metric_results[0].score == 9.0

    def test_evaluate_with_multiple_metrics(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric(), AlwaysFailMetric()])
        agent = FakeAgent()
        tc = TestCase(id="tc-1", name="Test 1", user_message="hello")

        result = engine.evaluate(agent, tc)
        assert result.passed is False
        assert len(result.metric_results) == 2

    def test_evaluate_agent_failure_returns_error_result(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FailingAgent()
        tc = TestCase(id="tc-1", name="Test 1", user_message="hello")

        result = engine.evaluate(agent, tc)
        assert result.passed is False
        assert result.execution.output == ""
        assert "Agent crashed" in result.execution.transcript

    def test_evaluate_batch_sequential(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FakeAgent()
        test_cases = self._make_test_cases(3)

        results = engine.evaluate_batch(agent, test_cases)
        assert len(results) == 3
        assert all(r.passed for r in results)
        assert results[0].test_case_id == "tc-0"
        assert results[2].test_case_id == "tc-2"

    def test_evaluate_batch_parallel(self):
        from eval_runner.engine import EvaluationEngine

        config = EvalConfig(max_workers=2)
        engine = EvaluationEngine(metrics=[AlwaysPassMetric()], config=config)
        agent = FakeAgent()
        test_cases = self._make_test_cases(5)

        results = engine.evaluate_batch(agent, test_cases)
        assert len(results) == 5
        ids = {r.test_case_id for r in results}
        assert ids == {"tc-0", "tc-1", "tc-2", "tc-3", "tc-4"}

    def test_evaluate_batch_with_failing_agent(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FailingAgent()
        test_cases = self._make_test_cases(2)

        results = engine.evaluate_batch(agent, test_cases)
        assert len(results) == 2
        assert all(not r.passed for r in results)

    def test_save_results_writes_json(self, tmp_path):
        from eval_runner.engine import EvaluationEngine

        config = EvalConfig(output_path=tmp_path / "results.json")
        engine = EvaluationEngine(metrics=[AlwaysPassMetric()], config=config)
        agent = FakeAgent()
        test_cases = self._make_test_cases(2)

        results = engine.evaluate_batch(agent, test_cases)
        engine.save_results(results)

        output_file = tmp_path / "results.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data["results"]) == 2
        assert "summary" in data

    def test_engine_from_config(self):
        from eval_runner.engine import EvaluationEngine

        config = EvalConfig(
            metrics=["assertion_pass_rate"],
            max_workers=2,
        )
        engine = EvaluationEngine.from_config(config)
        assert engine.config.max_workers == 2
        assert len(engine.metrics) == 1

    def test_summary_aggregation(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric(), AlwaysFailMetric()])
        agent = FakeAgent()
        test_cases = self._make_test_cases(3)

        results = engine.evaluate_batch(agent, test_cases)
        summary = engine.summarize(results)

        assert summary["total"] == 3
        assert summary["passed"] == 0  # AlwaysFailMetric fails all
        assert summary["failed"] == 3
        assert "per_metric" in summary
        assert "always_pass" in summary["per_metric"]
        assert "always_fail" in summary["per_metric"]
        assert summary["per_metric"]["always_pass"]["average_score"] == 9.0
        assert summary["per_metric"]["always_fail"]["average_score"] == 2.0

    def test_summary_backcompat_omits_new_keys(self):
        """summarize() with no test_cases stays back-compat (no per_complexity/per_tag)."""
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FakeAgent()
        results = engine.evaluate_batch(agent, self._make_test_cases(2))

        summary = engine.summarize(results)
        assert "per_complexity" not in summary
        assert "per_tag" not in summary

    def test_summary_per_complexity_and_per_tag(self):
        from eval_runner.engine import EvaluationEngine

        # Two passing (hard), one failing (easy). Tags overlap across cases so a
        # multi-tag result counts toward each of its tags.
        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FakeAgent()
        test_cases = [
            TestCase(id="tc-0", name="A", user_message="m0",
                     complexity="hard", tags=["a", "b"]),
            TestCase(id="tc-1", name="B", user_message="m1",
                     complexity="hard", tags=["b"]),
            TestCase(id="tc-2", name="C", user_message="m2",
                     complexity="easy", tags=[]),
        ]
        results = engine.evaluate_batch(agent, test_cases)
        summary = engine.summarize(results, test_cases)

        # per_complexity: single-valued bucket per result.
        assert summary["per_complexity"]["hard"]["total"] == 2
        assert summary["per_complexity"]["hard"]["passed"] == 2
        assert summary["per_complexity"]["hard"]["pass_rate"] == 1.0
        assert summary["per_complexity"]["hard"]["average_score"] == 9.0
        assert summary["per_complexity"]["easy"]["total"] == 1
        assert summary["per_complexity"]["easy"]["pass_rate"] == 1.0

        # per_tag: multi-valued — tc-0 contributes to both "a" and "b", so the
        # per-tag total (2 for "b") exceeds the number of results carrying tag-b
        # only once, and total tag count (3) exceeds result count (3 - 1 untagged).
        assert summary["per_tag"]["a"]["total"] == 1
        assert summary["per_tag"]["b"]["total"] == 2
        per_tag_total = sum(b["total"] for b in summary["per_tag"].values())
        assert per_tag_total == 3  # tc-0 (a,b) + tc-1 (b); tc-2 untagged contributes none
        assert per_tag_total > len(results) - 1

    def test_summary_per_complexity_mixed_pass(self):
        from eval_runner.engine import EvaluationEngine

        # Failing metric so every result fails — pass_rate 0, avg score 2.0.
        engine = EvaluationEngine(metrics=[AlwaysFailMetric()])
        agent = FakeAgent()
        test_cases = [
            TestCase(id="tc-0", name="A", user_message="m0",
                     complexity="hard", tags=["x"]),
            TestCase(id="tc-1", name="B", user_message="m1",
                     complexity="hard", tags=["x"]),
        ]
        results = engine.evaluate_batch(agent, test_cases)
        summary = engine.summarize(results, test_cases)

        assert summary["per_complexity"]["hard"]["total"] == 2
        assert summary["per_complexity"]["hard"]["passed"] == 0
        assert summary["per_complexity"]["hard"]["pass_rate"] == 0.0
        assert summary["per_complexity"]["hard"]["average_score"] == 2.0
        assert summary["per_tag"]["x"]["average_score"] == 2.0

    def test_summary_skips_result_not_in_test_cases(self):
        from eval_runner.engine import EvaluationEngine

        engine = EvaluationEngine(metrics=[AlwaysPassMetric()])
        agent = FakeAgent()
        test_cases = [
            TestCase(id="tc-0", name="A", user_message="m0", complexity="hard"),
        ]
        results = engine.evaluate_batch(agent, test_cases)
        # Summarize with an EMPTY by_id mapping — the result's id is unknown.
        summary = engine.summarize(results, test_cases=[])
        assert summary["per_complexity"] == {}
        assert summary["per_tag"] == {}
