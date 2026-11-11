# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for regression_report (compare_summaries + load_summary)."""

import json

import pytest

from eval_runner.regression_report import compare_summaries, load_summary


def _bucket(pass_rate: float, average_score: float) -> dict:
    return {
        "passed": 0,
        "total": 1,
        "pass_rate": pass_rate,
        "average_score": average_score,
    }


class TestCompareSummaries:
    def test_overall_regression_flagged(self):
        current = {"pass_rate": 0.50, "per_metric": {}, "per_complexity": {}, "per_tag": {}}
        baseline = {"pass_rate": 0.80, "per_metric": {}, "per_complexity": {}, "per_tag": {}}

        result = compare_summaries(current, baseline)
        assert result["overall"]["current"] == 0.50
        assert result["overall"]["baseline"] == 0.80
        assert result["overall"]["delta"] == pytest.approx(-0.30)
        assert result["overall"]["regressed"] is True
        assert result["has_regression"] is True

    def test_overall_no_regression_when_within_min_drop(self):
        current = {"pass_rate": 0.78, "per_metric": {}}
        baseline = {"pass_rate": 0.80, "per_metric": {}}

        result = compare_summaries(current, baseline, min_drop=0.05)
        assert result["overall"]["regressed"] is False
        assert result["has_regression"] is False

    @pytest.mark.parametrize(
        "current_pr, baseline_pr",
        [
            (0.45, 0.50),  # delta == -0.04999999999999993 (float noise below -0.05)
            (0.90, 0.95),  # delta == -0.04999999999999993
            (0.75, 0.80),  # delta == -0.050000000000000044
        ],
    )
    def test_exactly_min_drop_always_regresses(self, current_pr, baseline_pr):
        # A drop of exactly min_drop must regress regardless of which pass rates
        # produced it — the _EPS tolerance defends against float-subtraction noise.
        current = {"pass_rate": current_pr, "per_metric": {}}
        baseline = {"pass_rate": baseline_pr, "per_metric": {}}
        result = compare_summaries(current, baseline, min_drop=0.05)
        assert result["overall"]["regressed"] is True
        assert result["has_regression"] is True

    def test_bucket_statuses(self):
        current = {
            "pass_rate": 0.80,
            "per_metric": {
                "regressed_m": _bucket(0.40, 4.0),
                "improved_m": _bucket(0.95, 9.5),
                "unchanged_m": _bucket(0.70, 7.0),
                "new_m": _bucket(0.60, 6.0),
            },
            "per_complexity": {},
            "per_tag": {},
        }
        baseline = {
            "pass_rate": 0.80,
            "per_metric": {
                "regressed_m": _bucket(0.90, 9.0),
                "improved_m": _bucket(0.70, 7.0),
                "unchanged_m": _bucket(0.70, 7.0),
                "removed_m": _bucket(0.50, 5.0),
            },
            "per_complexity": {},
            "per_tag": {},
        }

        result = compare_summaries(current, baseline, min_drop=0.05)
        metrics = result["sections"]["per_metric"]

        assert metrics["regressed_m"]["status"] == "regressed"
        assert metrics["regressed_m"]["regressed"] is True
        assert metrics["regressed_m"]["pass_rate_delta"] == pytest.approx(-0.50)
        assert metrics["regressed_m"]["average_score_delta"] == pytest.approx(-5.0)

        assert metrics["improved_m"]["status"] == "improved"
        assert metrics["improved_m"]["regressed"] is False

        assert metrics["unchanged_m"]["status"] == "unchanged"
        assert metrics["unchanged_m"]["pass_rate_delta"] == pytest.approx(0.0)

        assert metrics["new_m"]["status"] == "new"
        assert metrics["new_m"]["pass_rate_delta"] is None
        assert metrics["new_m"]["regressed"] is False

        assert metrics["removed_m"]["status"] == "removed"
        assert metrics["removed_m"]["pass_rate_delta"] is None
        assert metrics["removed_m"]["regressed"] is False

        # Only the regressed metric bucket lands in the flat regressions list.
        assert result["regressions"] == ["per_metric/regressed_m"]
        assert result["has_regression"] is True

    def test_regression_in_complexity_and_tag_sections(self):
        current = {
            "pass_rate": 0.80,
            "per_complexity": {"hard": _bucket(0.40, 4.0)},
            "per_tag": {"auth": _bucket(0.30, 3.0)},
        }
        baseline = {
            "pass_rate": 0.80,
            "per_complexity": {"hard": _bucket(0.90, 9.0)},
            "per_tag": {"auth": _bucket(0.90, 9.0)},
        }

        result = compare_summaries(current, baseline)
        assert "per_complexity/hard" in result["regressions"]
        assert "per_tag/auth" in result["regressions"]
        assert result["has_regression"] is True

    def test_no_regression_clean_run(self):
        current = {
            "pass_rate": 0.90,
            "per_metric": {"m": _bucket(0.90, 9.0)},
            "per_complexity": {"easy": _bucket(1.0, 10.0)},
            "per_tag": {"t": _bucket(0.90, 9.0)},
        }
        baseline = {
            "pass_rate": 0.85,
            "per_metric": {"m": _bucket(0.85, 8.5)},
            "per_complexity": {"easy": _bucket(0.95, 9.5)},
            "per_tag": {"t": _bucket(0.85, 8.5)},
        }

        result = compare_summaries(current, baseline)
        assert result["regressions"] == []
        assert result["has_regression"] is False
        assert result["overall"]["delta"] == pytest.approx(0.05)

    def test_missing_sections_default_empty(self):
        # Summaries with no aggregation sections at all must not crash.
        result = compare_summaries({"pass_rate": 0.5}, {"pass_rate": 0.5})
        assert result["sections"]["per_metric"] == {}
        assert result["sections"]["per_complexity"] == {}
        assert result["sections"]["per_tag"] == {}
        assert result["has_regression"] is False


class TestLoadSummary:
    def test_load_roundtrip(self, tmp_path):
        path = tmp_path / "summary.json"
        payload = {"pass_rate": 0.75, "per_metric": {}}
        path.write_text(json.dumps(payload))

        assert load_summary(path) == payload

    def test_load_missing_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_summary(tmp_path / "does-not-exist.json")
