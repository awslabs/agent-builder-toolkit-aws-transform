# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in tool_usage metric.

Scores whether the agent invoked the tools a test case *expected* it to use and
avoided any it was *forbidden* from using. Both lists are read from the test
case's free-form ``metadata`` (no schema change):

- ``metadata.expected_tools``  — tool names that SHOULD be called.
- ``metadata.forbidden_tools`` — tool names that should NOT be called.

Like :class:`AssertionPassRateMetric`, this metric *abstains* (score 10.0, pass)
when a test case configures neither list, so it is safe to add to the default
metric set: it only "activates" for test cases that opt in. It is deterministic
and needs no LLM/Bedrock access.
"""

from __future__ import annotations

from eval_runner.metrics._metadata import coerce_str_list
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase

# Mirrors AssertionPassRateMetric / LLMJudgeMetric for cross-metric consistency.
_PASS_THRESHOLD = 7.0


class ToolUsageMetric:
    """Grades expected/forbidden tool invocations from ``metadata``.

    Satisfies :class:`eval_runner.metrics.interface.MetricInterface`.

    Each *expected* tool contributes one check (pass if it was called); each
    *forbidden* tool contributes one check (pass if it was NOT called). The score
    is ``(passes / total_checks) * 10.0`` and the metric passes at ``>= 7.0`` —
    the same fraction-based shape as ``assertion_pass_rate``.
    """

    @property
    def name(self) -> str:
        return "tool_usage"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        metadata = test_case.metadata or {}
        expected = coerce_str_list(metadata.get("expected_tools"))
        forbidden = coerce_str_list(metadata.get("forbidden_tools"))

        if not expected and not forbidden:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no expected_tools/forbidden_tools in metadata"},
            )

        called = _called_tool_names(execution)
        checks: list[dict] = []
        passes = 0

        for tool in expected:
            ok = tool in called
            checks.append({"tool": tool, "kind": "expected", "called": ok, "passed": ok})
            if ok:
                passes += 1

        for tool in forbidden:
            used = tool in called
            ok = not used
            checks.append({"tool": tool, "kind": "forbidden", "called": used, "passed": ok})
            if ok:
                passes += 1

        total = len(checks)
        score = (passes / total) * 10.0
        passed = score >= _PASS_THRESHOLD
        missing = [c["tool"] for c in checks if c["kind"] == "expected" and not c["passed"]]
        violated = [c["tool"] for c in checks if c["kind"] == "forbidden" and not c["passed"]]
        evidence_parts = []
        if missing:
            evidence_parts.append(f"expected but not called: {missing}")
        if violated:
            evidence_parts.append(f"forbidden but called: {violated}")
        evidence = "; ".join(evidence_parts) if evidence_parts else "all tool checks passed"
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "checks": checks,
                "tools_called": sorted(called),
                "assertions": [
                    {"name": "tool_usage", "passed": passed, "reason": evidence}
                ],
            },
        )


def _called_tool_names(execution: ExecutionResult) -> set[str]:
    """Collect the set of tool names invoked during the run.

    Reads the ``name`` key, matching how ``AssertionPassRateMetric`` grades
    ``tool_called`` assertions — the two deterministic metrics stay consistent.
    """
    return {
        name
        for tc in execution.tool_calls
        if (name := (tc.get("name") or "").strip())
    }
