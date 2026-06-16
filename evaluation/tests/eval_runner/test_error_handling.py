# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ErrorHandlingMetric (task 2.3)."""

from eval_runner.metrics.error_handling import ErrorHandlingMetric
from eval_runner.models import ExecutionResult
from eval_runner.test_case import TestCase


class TestErrorHandlingMetric:
    def _make_execution(self, transcript: str = "") -> ExecutionResult:
        return ExecutionResult(transcript=transcript, output="")

    def _make_tc(self, metadata: dict | None = None) -> TestCase:
        return TestCase(
            id="t1", name="test", user_message="hi", metadata=metadata or {}
        )

    def test_clean_transcript_passes(self):
        metric = ErrorHandlingMetric()
        execution = self._make_execution(transcript="Agent: all steps completed fine")
        result = metric.evaluate(execution, self._make_tc())
        assert result.score == 10.0
        assert result.passed is True
        assert result.details["errors_found"] == []
        # Clean path reports which markers were checked (just the narrow default).
        assert result.details["markers_checked"] == ["ERROR:"]

    def test_error_marker_fails(self):
        """The real timeout failure shape: 'ERROR: Exceeded 300s'."""
        metric = ErrorHandlingMetric()
        execution = self._make_execution(transcript="agent: ERROR: Exceeded 300s")
        result = metric.evaluate(execution, self._make_tc())
        assert result.score == 0.0
        assert result.passed is False
        assert "ERROR:" in result.details["errors_found"]

    def test_case_insensitive_match(self):
        metric = ErrorHandlingMetric()
        execution = self._make_execution(transcript="agent: error: it broke")  # lowercase
        result = metric.evaluate(execution, self._make_tc())
        assert result.passed is False

    def test_broad_markers_not_default_tripped(self):
        """The narrowed default is ERROR: only — prose discussing Exception/FATAL/
        panic/Traceback must NOT false-positive (the bug this fix closes)."""
        metric = ErrorHandlingMetric()
        prose = (
            "agent: the first deploy threw an Exception: connection reset, "
            "so I retried; set the log level to FATAL and the Go handler may "
            "panic: on nil. Traceback (most recent call last) was reviewed."
        )
        result = metric.evaluate(self._make_execution(transcript=prose), self._make_tc())
        assert result.score == 10.0
        assert result.passed is True
        assert result.details["errors_found"] == []

    def test_active_without_config(self):
        """Unlike tool_usage/completeness, error_handling needs no metadata to act."""
        metric = ErrorHandlingMetric()
        execution = self._make_execution(transcript="ERROR: boom")
        result = metric.evaluate(execution, self._make_tc(metadata={}))
        assert result.passed is False

    def test_custom_markers_override(self):
        metric = ErrorHandlingMetric()
        tc = self._make_tc({"error_markers": ["CUSTOM_FAIL"]})
        # Default markers should no longer trip when an override is supplied...
        clean = metric.evaluate(self._make_execution(transcript="ERROR: ignored"), tc)
        assert clean.passed is True
        # ...but the custom marker does.
        dirty = metric.evaluate(self._make_execution(transcript="got CUSTOM_FAIL here"), tc)
        assert dirty.passed is False
        assert "CUSTOM_FAIL" in dirty.details["errors_found"]

    def test_empty_override_falls_back_to_defaults(self):
        """An empty/blank override must not silently disable the check."""
        metric = ErrorHandlingMetric()
        tc = self._make_tc({"error_markers": []})
        result = metric.evaluate(self._make_execution(transcript="ERROR: boom"), tc)
        assert result.passed is False

    def test_single_string_marker_coerced(self):
        metric = ErrorHandlingMetric()
        tc = self._make_tc({"error_markers": "denied"})
        result = metric.evaluate(self._make_execution(transcript="access DENIED"), tc)
        assert result.passed is False

    def test_name(self):
        assert ErrorHandlingMetric().name == "error_handling"
