# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""llm_judge metric — scores a transcript using the eval_framework LLM judge.

Wraps the ACP engine's judge agent as a pluggable
:class:`MetricInterface`, so the LLM-as-judge becomes *one metric among many*
rather than a separate, baked-in grading path. It reduces the judge's
per-assertion verdicts to a single 0–10 score (fraction passed × 10) and a
pass/fail, mirroring the deterministic ``assertion_pass_rate`` metric so the two
are interchangeable and combinable in :class:`EvaluationEngine`.

Construction requires a framework orchestrator (or config) to reach the judge.
Because metrics are resolved by name through :class:`MetricRegistry` (which
constructs them with no args), this metric is registered as a *factory bound to a
config* by the engine wiring rather than discovered zero-arg; see
``MetricRegistry.register`` usage in the CLI/engine setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase

if TYPE_CHECKING:
    from eval_runner.config import ExecutionConfig
    from eval_runner.execution.runner import EvalOrchestrator

# Pass threshold mirrors AssertionPassRateMetric for consistency across metrics.
_PASS_THRESHOLD = 7.0


class LLMJudgeMetric:
    """Grades a transcript with the framework's LLM judge agent.

    Satisfies :class:`eval_runner.metrics.interface.MetricInterface`.
    """

    def __init__(
        self,
        execution_config: "ExecutionConfig | None" = None,
        orchestrator: "EvalOrchestrator | None" = None,
        cwd: str = "/tmp",
        verbose: bool = False,
    ) -> None:
        """Initialize the judge metric.

        Args:
            execution_config: ExecutionConfig describing the judge agent and ACP
                driver. Required unless ``orchestrator`` is supplied.
            orchestrator: Pre-built orchestrator (mainly for testing / sharing the
                ACPAgent's orchestrator). When None, one is built from
                ``execution_config``.
            cwd: Working directory for the judge bridge session.
            verbose: Enable debug logging for the ACP driver.
        """
        if execution_config is None and orchestrator is None:
            raise ValueError("LLMJudgeMetric requires execution_config or orchestrator")
        self.execution_config = execution_config
        self._orchestrator = orchestrator
        self.cwd = cwd
        self.verbose = verbose

    @property
    def name(self) -> str:
        return "llm_judge"

    @property
    def orchestrator(self) -> "EvalOrchestrator":
        if self._orchestrator is None:
            from eval_runner.execution.runner import EvalOrchestrator

            self._orchestrator = EvalOrchestrator(
                config=self.execution_config,
                cwd=self.cwd,
                verbose=self.verbose,
            )
        return self._orchestrator

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        from eval_runner.models import AssertionResultStatus

        assertions = test_case.assertions
        if not assertions:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no assertions defined"},
            )

        # The judge consumes the same formatted transcript string that the
        # ACPAgent stored on ExecutionResult.transcript — no re-run needed.
        results, _log_path, _session_id = self.orchestrator.grade_transcript(
            execution.transcript,
            assertions,
            eval_id=test_case.id,
        )

        passed = sum(1 for a in results if a.result == AssertionResultStatus.PASS)
        total = len(results) or len(assertions)
        score = (passed / total) * 10.0 if total else 0.0

        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= _PASS_THRESHOLD,
            details={
                "assertions": [
                    {
                        "name": a.name,
                        "result": a.result.value,
                        "evidence": a.evidence,
                        "turn_number": a.turn_number,
                    }
                    for a in results
                ]
            },
        )
