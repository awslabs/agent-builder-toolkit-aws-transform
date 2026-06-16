# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Built-in error_handling metric.

Scores whether the run completed without a *framework-level* error surfacing in
the transcript — i.e. error absence, not the agent's error-recovery quality.
Unlike :mod:`tool_usage` and :mod:`completeness`, this metric is *always active*:
a transcript free of framework errors is the universal expectation, so it needs
no per-test config.

By default it scans for ``ERROR:`` only. That is the one marker the ACP engine
actually writes when a turn fails or times out (see ``execution/runner.py`` and
``engine.py``; the curated sample asserts ``transcript_not_contains: "ERROR:"``
by the same convention). The default is intentionally narrow: a broad set like
``Exception:`` / ``FATAL`` / ``panic:`` would false-positive on ordinary agent
prose that merely *discusses* such terms. A test case that wants stricter or
domain-specific markers can supply ``metadata.error_markers`` (a list of
substrings, matched case-insensitively), which *replaces* the default.
Deterministic; no LLM access.
"""

from __future__ import annotations

from eval_runner.metrics._metadata import coerce_str_list
from eval_runner.models import ExecutionResult, MetricResult
from eval_runner.test_case import TestCase

# No pass threshold: this metric is binary — a clean transcript scores 10.0
# (pass), any surfaced framework error scores 0.0 (fail).

# The single marker the ACP engine actually emits on a failed/timed-out turn
# (runner.py writes "ERROR: ..." into the agent entry; engine.py uses the same
# prefix). Matched case-insensitively. Deliberately narrow — broader markers
# (Exception:/FATAL/panic:/Traceback) false-positive on agent prose that merely
# discusses errors; a test case opts into those via metadata.error_markers.
_DEFAULT_ERROR_MARKERS: tuple[str, ...] = ("ERROR:",)


class ErrorHandlingMetric:
    """Penalizes error markers found in the transcript.

    Satisfies :class:`eval_runner.metrics.interface.MetricInterface`.

    A transcript with no error markers scores 10.0 (pass). Any marker present
    drops the score to 0.0 (fail): a surfaced framework error is a binary
    health signal, not a graded fraction. The matched markers are reported in
    ``details`` for triage.
    """

    @property
    def name(self) -> str:
        return "error_handling"

    def evaluate(self, execution: ExecutionResult, test_case: TestCase) -> MetricResult:
        metadata = test_case.metadata or {}
        markers = _resolve_markers(metadata.get("error_markers"))

        haystack = execution.transcript.lower()
        found = [m for m in markers if m.lower() in haystack]

        if found:
            evidence = f"error markers found in transcript: {found}"
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                details={
                    "errors_found": found,
                    "assertions": [
                        {"name": "error_handling", "passed": False, "reason": evidence}
                    ],
                },
            )

        return MetricResult(
            metric_name=self.name,
            score=10.0,
            passed=True,
            details={
                "errors_found": [],
                "markers_checked": list(markers),
                "assertions": [
                    {"name": "error_handling", "passed": True, "reason": "no error markers found"}
                ],
            },
        )


def _resolve_markers(value: object) -> tuple[str, ...]:
    """Use the test case's ``error_markers`` override if provided, else defaults.

    An empty or invalid override falls back to :data:`_DEFAULT_ERROR_MARKERS`
    rather than disabling the check (silently scoring everything as clean would
    be a worse default).
    """
    return tuple(coerce_str_list(value)) or _DEFAULT_ERROR_MARKERS
