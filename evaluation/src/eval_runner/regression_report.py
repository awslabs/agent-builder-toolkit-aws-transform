# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compare an eval summary against a baseline to flag pass-rate regressions.

Pure, deterministic helpers over the summary dicts produced by
:meth:`eval_runner.engine.EvaluationEngine.summarize`. :func:`compare_summaries`
diffs the overall pass rate plus each aggregation section
(``per_metric``/``per_complexity``/``per_tag``) bucket-by-bucket; a bucket is a
regression when its pass rate drops by more than ``min_drop``. The only I/O is
:func:`load_summary`, which reads a persisted ``summary.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

# Aggregation sections compared bucket-by-bucket, in a deterministic order.
_SECTIONS = ("per_metric", "per_complexity", "per_tag")

# Tolerance so a drop of *exactly* min_drop counts as a regression regardless of
# float-subtraction noise (e.g. 0.45 - 0.50 == -0.04999999999999993). Without it,
# whether a dead-on threshold trips would vary by which pass rates produced it.
_EPS = 1e-9


def load_summary(path: str | Path) -> dict:
    """Load a persisted ``summary.json``.

    Raises ``FileNotFoundError`` (cleanly) if the file is missing — the caller
    is expected to catch it and degrade gracefully.
    """
    return json.loads(Path(path).read_text())


def compare_summaries(
    current: dict, baseline: dict, *, min_drop: float = 0.05
) -> dict:
    """Diff ``current`` against ``baseline`` and flag pass-rate regressions.

    For every bucket present in BOTH summaries, computes the pass-rate and
    average-score deltas (current - baseline). A bucket is flagged as a
    regression when its pass-rate drops by ``min_drop`` or more (delta
    ``<= -min_drop``, within a small float tolerance). Buckets present only in
    ``current`` are "new" (never a regression); buckets only in ``baseline`` are
    "removed".

    Returns a deterministic dict::

        {
          "overall": {"current", "baseline", "delta", "regressed"},
          "sections": {section: {bucket: {"pass_rate_delta", "average_score_delta",
                                          "regressed", "status"}}},
          "regressions": ["<section>/<bucket>", ...],
          "has_regression": bool,
        }
    """
    cur_overall = current.get("pass_rate", 0.0)
    base_overall = baseline.get("pass_rate", 0.0)
    overall_delta = cur_overall - base_overall
    overall_regressed = overall_delta <= -min_drop + _EPS

    sections: dict[str, dict] = {}
    regressions: list[str] = []

    for section in _SECTIONS:
        cur_section = current.get(section, {})
        base_section = baseline.get(section, {})
        bucket_keys = sorted(set(cur_section) | set(base_section))

        section_out: dict[str, dict] = {}
        for key in bucket_keys:
            in_cur = key in cur_section
            in_base = key in base_section
            if in_cur and in_base:
                pr_delta = cur_section[key].get("pass_rate", 0.0) - base_section[
                    key
                ].get("pass_rate", 0.0)
                score_delta = cur_section[key].get("average_score", 0.0) - base_section[
                    key
                ].get("average_score", 0.0)
                regressed = pr_delta <= -min_drop + _EPS
                if regressed:
                    status = "regressed"
                elif pr_delta > 0:
                    status = "improved"
                else:
                    status = "unchanged"
            elif in_cur:
                pr_delta = None
                score_delta = None
                regressed = False
                status = "new"
            else:  # only in baseline
                pr_delta = None
                score_delta = None
                regressed = False
                status = "removed"

            section_out[key] = {
                "pass_rate_delta": pr_delta,
                "average_score_delta": score_delta,
                "regressed": regressed,
                "status": status,
            }
            if regressed:
                regressions.append(f"{section}/{key}")

        sections[section] = section_out

    has_regression = overall_regressed or bool(regressions)

    return {
        "overall": {
            "current": cur_overall,
            "baseline": base_overall,
            "delta": overall_delta,
            "regressed": overall_regressed,
        },
        "sections": sections,
        "regressions": regressions,
        "has_regression": has_regression,
    }
