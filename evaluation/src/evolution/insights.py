# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter for the ``insights`` verb — root-cause diagnosis of an eval run.

The "insights" engine is the evolver's analyst (``harness_evolver.analyst.analyze``):
given an artifacts directory (eval run outputs) and a goal, it inspects the
evidence and writes a diagnostic ``report.md`` (root causes + citations + a
structured summary block). This is the same diagnosis the evolver feeds itself
each step — surfaced here as a standalone command so you can run it against any
eval-results directory without launching an evolution loop.
"""

from __future__ import annotations

from pathlib import Path


def generate_insights(
    *,
    artifacts_dir: Path,
    goal: str,
    output_dir: Path | None = None,
    target_dir: Path | None = None,
) -> tuple[str, Path]:
    """Run the analyst over an artifacts dir and write report.md.

    Args:
        artifacts_dir: Directory of eval evidence (transcripts, results, summary).
        goal: What success looks like (guides the analyst's diagnosis).
        output_dir: Where report.md is written (default: ``<artifacts_dir>/insights``).
        target_dir: Optional read-only agent source the analyst may inspect to
            explain mechanism.

    Returns:
        (report_text, report_path)
    """
    import anyio
    from harness_evolver.analyst import analyze

    artifacts_dir = Path(artifacts_dir).resolve()
    output_dir = Path(output_dir).resolve() if output_dir else artifacts_dir / "insights"

    return anyio.run(
        lambda: analyze(
            artifacts_dir=artifacts_dir,
            goal=goal,
            output_dir=output_dir,
            target_dir=Path(target_dir).resolve() if target_dir else None,
        )
    )
