# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""EvaluationEngine — executes test cases, scores with metrics, aggregates results."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from eval_runner.agent_interface import EvalAgentInterface
from eval_runner.config import EvalConfig
from eval_runner.metrics.interface import MetricInterface
from eval_runner.metrics.registry import MetricRegistry
from eval_runner.models import EvaluationResult, ExecutionResult, MetricResult
from eval_runner.test_case import TestCase

logger = logging.getLogger(__name__)


class EvaluationEngine:
    """Runs test cases against an agent and scores with metrics."""

    def __init__(
        self,
        metrics: list[MetricInterface],
        config: EvalConfig | None = None,
    ) -> None:
        self.metrics = metrics
        self.config = config or EvalConfig()

    @classmethod
    def from_config(cls, config: EvalConfig) -> EvaluationEngine:
        registry = MetricRegistry()
        # The llm_judge metric needs the ACP orchestrator; bind it at wiring time
        # when the config carries an execution_config (ACP execution path).
        if config.execution_config is not None and "llm_judge" in config.metrics:
            from eval_runner.metrics.llm_judge import LLMJudgeMetric

            execution_config = config.execution_config
            registry.register_factory(
                "llm_judge", lambda: LLMJudgeMetric(execution_config=execution_config)
            )
        metrics = registry.resolve(config.metrics)
        return cls(metrics=metrics, config=config)

    def evaluate(
        self, agent: EvalAgentInterface, test_case: TestCase
    ) -> EvaluationResult:
        execution, errored = self._execute_safe(agent, test_case)
        if errored:
            metric_results = [
                MetricResult(
                    metric_name=m.name, score=0.0, passed=False,
                    details={"error": "agent execution failed"},
                )
                for m in self.metrics
            ]
        else:
            metric_results = self._score(execution, test_case)
        return EvaluationResult(
            test_case_id=test_case.id,
            execution=execution,
            metric_results=metric_results,
        )

    def evaluate_batch(
        self, agent: EvalAgentInterface, test_cases: list[TestCase]
    ) -> list[EvaluationResult]:
        max_workers = self.config.max_workers
        if max_workers > 1:
            return self._batch_parallel(agent, test_cases, max_workers)
        return self._batch_sequential(agent, test_cases)

    def summarize(self, results: list[EvaluationResult]) -> dict:
        total = len(results)
        passed = sum(1 for r in results if r.passed)

        per_metric: dict[str, dict] = {}
        for result in results:
            for mr in result.metric_results:
                if mr.metric_name not in per_metric:
                    per_metric[mr.metric_name] = {"scores": [], "passed": 0, "total": 0}
                per_metric[mr.metric_name]["scores"].append(mr.score)
                per_metric[mr.metric_name]["total"] += 1
                if mr.passed:
                    per_metric[mr.metric_name]["passed"] += 1

        for name, data in per_metric.items():
            scores = data.pop("scores")
            data["average_score"] = sum(scores) / len(scores) if scores else 0.0
            data["pass_rate"] = data["passed"] / data["total"] if data["total"] else 0.0

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "per_metric": per_metric,
        }

    def save_results(self, results: list[EvaluationResult]) -> None:
        output_path = self.config.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        summary = self.summarize(results)
        data = {
            "summary": summary,
            "results": [self._result_to_dict(r) for r in results],
        }
        output_path.write_text(json.dumps(data, indent=2))

    def _execute_safe(
        self, agent: EvalAgentInterface, test_case: TestCase
    ) -> tuple[ExecutionResult, bool]:
        try:
            result = agent.execute(test_case)
            return result, False
        except Exception as e:
            logger.warning(f"Agent failed on {test_case.id}: {e}")
            return ExecutionResult(
                transcript=f"ERROR: {e}",
                output="",
            ), True

    def _score(
        self, execution: ExecutionResult, test_case: TestCase
    ) -> list[MetricResult]:
        results = []
        for metric in self.metrics:
            try:
                results.append(metric.evaluate(execution, test_case))
            except Exception as e:
                logger.warning(f"Metric {metric.name} failed: {e}")
                results.append(
                    MetricResult(
                        metric_name=metric.name,
                        score=0.0,
                        passed=False,
                        details={"error": str(e)},
                    )
                )
        return results

    def _batch_sequential(
        self, agent: EvalAgentInterface, test_cases: list[TestCase]
    ) -> list[EvaluationResult]:
        return [self.evaluate(agent, tc) for tc in test_cases]

    def _batch_parallel(
        self,
        agent: EvalAgentInterface,
        test_cases: list[TestCase],
        max_workers: int,
    ) -> list[EvaluationResult]:
        results: list[EvaluationResult | None] = [None] * len(test_cases)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.evaluate, agent, tc): i
                for i, tc in enumerate(test_cases)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = EvaluationResult(
                        test_case_id=test_cases[idx].id,
                        execution=ExecutionResult(transcript=f"ERROR: {e}", output=""),
                        metric_results=[
                            MetricResult(
                                metric_name=m.name, score=0.0, passed=False,
                                details={"error": "parallel execution failed"},
                            )
                            for m in self.metrics
                        ],
                    )

        return results  # type: ignore[return-value]

    @staticmethod
    def _result_to_dict(result: EvaluationResult) -> dict:
        return {
            "test_case_id": result.test_case_id,
            "passed": result.passed,
            "execution": {
                "transcript": result.execution.transcript,
                "output": result.execution.output,
                "tool_calls": result.execution.tool_calls,
                "duration_ms": result.execution.duration_ms,
                "turn_count": result.execution.turn_count,
            },
            "metrics": [
                {
                    "metric_name": mr.metric_name,
                    "score": mr.score,
                    "passed": mr.passed,
                    "details": mr.details,
                }
                for mr in result.metric_results
            ],
        }
