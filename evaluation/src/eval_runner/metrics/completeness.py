# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in completeness metric.

Scores whether a run reached its *designed* end rather than being truncated by
the turn budget. The signal is the turn count: the ACP engine ends a scenario
early when the simulated user is satisfied (it emits a ``__DONE__`` sentinel and
the orchestrator breaks — see ``execution/runner.py``), so a run that finishes
on its own stops *below* ``max_turns``, while a run that is cut off hits the
ceiling. Two equally-weighted checks when the metric is active:

1. the run did not exhaust its turn budget (``turn_count < max_turns``), and
2. the agent's final output is non-empty (a non-truncated last turn).

Note the ``__DONE__`` sentinel is consumed by the orchestrator and never lands
in the transcript, so this metric deliberately does *not* key off it. A test
case may still supply ``metadata.completion_markers`` to additionally require an
explicit substring in the transcript (matched case-insensitively); when set, the
marker replaces the turn-budget check as the first signal.

The metric *abstains* (score 10.0, pass) when it has no signal to act on —
neither ``completion_markers`` nor a usable ``turn_count``/``max_turns`` — so it
is safe to add to the default metric set; it only "activates" when the backend
reports turn counts or the test opts in via metadata. Deterministic; no
LLM/Bedrock access.
"""

from __future__ import annotations

from eval_runner.metrics._metadata import coerce_str_list
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase

# Mirrors the other metrics' pass threshold for cross-metric consistency.
_PASS_THRESHOLD = 7.0


class CompletenessMetric:
    """Grades whether the run reached its designed completion.

    Satisfies :class:`eval_runner.metrics.interface.MetricInterface`.

    Two checks contribute equally when the metric is active: the run completed
    (did not hit the turn ceiling, or an explicit completion marker is present)
    and the final output is non-empty. Score is ``(passes / 2) * 10.0``
    (10.0 both / 5.0 one / 0.0 neither), passing at ``>= 7.0`` — so both
    conditions must hold to pass.
    """

    @property
    def name(self) -> str:
        return "completeness"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        metadata = test_case.metadata or {}
        markers = coerce_str_list(metadata.get("completion_markers"))

        completed, signal = self._completed(execution, test_case, markers)
        if completed is None:
            return MetricResult(
                metric_name=self.name,
                score=10.0,
                passed=True,
                details={"reason": "no completion signal (no markers, no turn_count)"},
            )

        output_ok = bool(execution.output.strip())
        passes = int(completed) + int(output_ok)
        score = (passes / 2) * 10.0
        passed = score >= _PASS_THRESHOLD
        parts = []
        if not completed:
            parts.append(f"run did not complete ({signal})")
        if not output_ok:
            parts.append("final output is empty")
        evidence = "; ".join(parts) if parts else f"completed ({signal}) with non-empty output"
        details: dict = {
            "completed": completed,
            "completion_signal": signal,
            "output_non_empty": output_ok,
            "assertions": [
                {"name": "completeness", "passed": passed, "reason": evidence}
            ],
        }
        if markers:
            details["matched_markers"] = [
                m for m in markers if m.lower() in execution.transcript.lower()
            ]
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=passed,
            details=details,
        )

    @staticmethod
    def _completed(
        execution: ExecutionResult, test_case: TestCase, markers: list[str]
    ) -> tuple[bool | None, str]:
        """Decide whether the run reached its designed end.

        Returns ``(completed, signal)`` where ``completed`` is ``None`` when no
        completion signal is available (caller abstains) and ``signal`` names
        the basis used. An explicit completion marker, when configured, takes
        precedence over the turn-budget heuristic.
        """
        if markers:
            haystack = execution.transcript.lower()
            return any(m.lower() in haystack for m in markers), "marker"

        # Turn-budget heuristic: a run that ended on its own stops below the
        # ceiling; one truncated by max_turns reaches it. Needs a tracked turn
        # count and >= 2 turns of headroom — a single-turn budget (max_turns<=1)
        # leaves no room to end early, so the heuristic carries no signal.
        turn_count = execution.turn_count
        max_turns = test_case.max_turns
        if turn_count is not None and max_turns and max_turns > 1:
            return turn_count < max_turns, "turn_budget"

        return None, "none"
