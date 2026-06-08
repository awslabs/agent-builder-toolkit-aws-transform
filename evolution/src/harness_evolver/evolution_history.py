# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Evolution History Tracker

Tracks cross-iteration evaluation metrics and evolution decisions in a human-readable
markdown file. Provides cumulative context for the evolver agent to avoid repeating
mistakes and build on successes.

Usage:
    history = EvolutionHistory(run_dir / "evolution_history.md")

    # Before evolution
    history.record_evaluation(
        step=1,
        train_stats=stats,
        validation_stats=val_stats,
        diff=diff_from_prev_step,
    )

    # After evolution
    history.record_evolution(
        step=1,
        changes_summary="Updated system prompt to handle edge cases...",
    )
"""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class EvaluationStats:
    """Statistics from running an environment evaluation."""

    pass_rate: float
    n_pass: int
    n_fail: int
    n_total: int
    passed_tasks: list[str] | None = None
    failed_tasks: list[str] | None = None

    @classmethod
    def from_summary_json(cls, summary_path: Path) -> EvaluationStats | None:
        """Parse evaluation_summary.json into EvaluationStats."""
        if not summary_path.exists():
            return None

        try:
            with summary_path.open() as f:
                data = json.load(f)

            tests = data.get("tests", [])
            # Evaluation summaries identify tasks by "test_id"; tolerate "name"
            # as a fallback for any alternate schema.
            def _task_name(t: dict) -> str:
                return t.get("test_id") or t.get("name") or "<unknown>"

            passed_tasks = [_task_name(t) for t in tests if t.get("passed", False)]
            failed_tasks = [_task_name(t) for t in tests if not t.get("passed", False)]

            return cls(
                pass_rate=data.get("assertion_pass_rate", 0.0),
                n_pass=len(passed_tasks),
                n_fail=len(failed_tasks),
                n_total=data.get("total_tests", len(tests)),
                passed_tasks=passed_tasks,
                failed_tasks=failed_tasks,
            )
        except Exception:
            return None


@dataclass
class StepDiff:
    """Comparison between current and previous step."""

    flipped: list[str]  # fail -> pass
    regressed: list[str]  # pass -> fail
    stable_pass: list[str]  # pass -> pass
    stable_fail: list[str]  # fail -> fail

    @property
    def net_change(self) -> int:
        """Net improvement (positive = better)."""
        return len(self.flipped) - len(self.regressed)

    @property
    def retention_rate(self) -> float:
        """Percentage of previously passing tasks still passing."""
        prev_passing = len(self.stable_pass) + len(self.regressed)
        if prev_passing == 0:
            return 1.0
        return len(self.stable_pass) / prev_passing

    @classmethod
    def compute(
        cls,
        current: EvaluationStats,
        previous: EvaluationStats | None,
    ) -> StepDiff | None:
        """Compute diff between current and previous stats."""
        if previous is None or current.passed_tasks is None or previous.passed_tasks is None:
            return None

        curr_passed = set(current.passed_tasks)
        curr_failed = set(current.failed_tasks or [])
        prev_passed = set(previous.passed_tasks)
        prev_failed = set(previous.failed_tasks or [])

        flipped = sorted(prev_failed & curr_passed)
        regressed = sorted(prev_passed & curr_failed)
        stable_pass = sorted(prev_passed & curr_passed)
        stable_fail = sorted(prev_failed & curr_failed)

        return cls(
            flipped=flipped,
            regressed=regressed,
            stable_pass=stable_pass,
            stable_fail=stable_fail,
        )


class EvolutionHistory:
    """Maintains evolution_history.md with cumulative iteration tracking."""

    def __init__(self, path: Path, snapshots_dir: Path | None = None):
        """Initialize evolution history tracker.

        Args:
            path: Path to evolution_history.md
            snapshots_dir: Optional path to snapshots.git directory for on-demand code access
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir = Path(snapshots_dir) if snapshots_dir else None

        if not self.path.exists():
            self._init_file()

    def _init_file(self) -> None:
        """Initialize empty history file with header."""
        self.path.write_text(
            "# Harness Evolution History\n\n"
            "This file tracks the evolution of the agent harness across training steps.\n"
            "Each entry shows evaluation results, cross-step changes, and evolution decisions.\n\n"
        )

    def record_evaluation(
        self,
        step: int,
        train_stats: EvaluationStats,
        validation_stats: EvaluationStats | None = None,
        diff: StepDiff | None = None,
        metadata: dict[str, Any] | None = None,
        snapshot_sha: str | None = None,
    ) -> None:
        """Record evaluation results before evolution runs.

        Args:
            step: Current step number
            train_stats: Training evaluation statistics
            validation_stats: Optional validation evaluation statistics
            diff: Optional comparison with previous step
            metadata: Optional additional metadata (e.g., early_stopping_triggered)
            snapshot_sha: Optional git snapshot SHA for code state
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"## Step {step} — {now}\n"]

        # Training metrics
        lines.append(f"**Training**: {train_stats.pass_rate:.1%} pass rate "
                    f"({train_stats.n_pass}/{train_stats.n_total} tasks)")

        # Validation metrics (if available)
        if validation_stats:
            lines.append(f"**Validation**: {validation_stats.pass_rate:.1%} pass rate "
                        f"({validation_stats.n_pass}/{validation_stats.n_total} tasks)")

        # Cross-step changes
        if diff:
            lines.append(f"\n**Changes from Step {step - 1}**:")
            lines.append(f"- Net change: {diff.net_change:+d} "
                        f"({len(diff.flipped)} flipped, {len(diff.regressed)} regressed)")

            if len(diff.stable_pass) + len(diff.regressed) > 0:
                lines.append(f"- Retention rate: {diff.retention_rate:.1%} "
                            f"({len(diff.stable_pass)}/{len(diff.stable_pass) + len(diff.regressed)} "
                            f"previously passing tasks still passing)")

            if diff.flipped:
                lines.append(f"- 🎉 Flipped (fail→pass): {', '.join(diff.flipped[:10])}"
                           + ("..." if len(diff.flipped) > 10 else ""))

            if diff.regressed:
                lines.append(f"- 🔴 Regressed (pass→fail): {', '.join(diff.regressed[:10])}"
                           + ("..." if len(diff.regressed) > 10 else ""))

            if diff.stable_pass:
                lines.append(f"- 🛡️ Stable pass: {len(diff.stable_pass)} tasks")

            if diff.stable_fail:
                lines.append(f"- 📌 Stable fail: {len(diff.stable_fail)} tasks")

        # Task breakdown
        lines.append(f"\n**Task Details**:")
        if train_stats.passed_tasks:
            task_list = ', '.join(train_stats.passed_tasks[:15])
            if len(train_stats.passed_tasks) > 15:
                task_list += f"... (+{len(train_stats.passed_tasks) - 15} more)"
            lines.append(f"- ✅ Passed ({len(train_stats.passed_tasks)}): {task_list}")

        if train_stats.failed_tasks:
            task_list = ', '.join(train_stats.failed_tasks[:15])
            if len(train_stats.failed_tasks) > 15:
                task_list += f"... (+{len(train_stats.failed_tasks) - 15} more)"
            lines.append(f"- ❌ Failed ({len(train_stats.failed_tasks)}): {task_list}")

        # Metadata
        if metadata:
            if metadata.get("final_eval"):
                lines.append(f"\n🏁 **Final evaluation** (no further evolution after this step)")
            if metadata.get("early_stopping_triggered"):
                lines.append(f"\n⚠️ **Early stopping triggered** "
                           f"(best step: {metadata.get('best_validation_step', '?')})")

        # Snapshot reference (if available)
        if snapshot_sha and self.snapshots_dir:
            # Check if we should highlight the need for code inspection
            inspection_note = ""

            # Signal 1: Validation divergence (overfitting)
            if validation_stats and diff:
                train_improved = train_stats.pass_rate > (validation_stats.pass_rate + 0.05)
                if train_improved:
                    inspection_note = " 🚨 **INSPECT**: Validation divergence detected - check for overfitting"

            # Signal 2: Regression after success
            if diff and diff.regressed:
                if not inspection_note:
                    inspection_note = " ⚠️ **INSPECT**: Tasks regressed - verify changes"

            lines.append(f"\n*Code snapshot*: `{snapshot_sha[:12]}` "
                        f"(view with: `git --git-dir={self.snapshots_dir} show {snapshot_sha[:12]}`)"
                        f"{inspection_note}")

        lines.append("\n")

        with self.path.open("a") as f:
            f.write("\n".join(lines))

    def record_evolution(
        self,
        step: int,
        changes_summary: str,
        rationale: str | None = None,
        edits: list[str] | None = None,
    ) -> None:
        """Record evolution decisions after evolver agent runs.

        Args:
            step: Current step number
            changes_summary: High-level summary of what changed
            rationale: Optional detailed rationale from evolver
            edits: Optional list of edited files
        """
        lines = ["**Evolution Output**:\n"]

        if rationale:
            lines.append(f"*Rationale*: {rationale}\n")

        lines.append(changes_summary)

        if edits:
            lines.append(f"\n*Files modified*: {', '.join(edits[:10])}"
                        + ("..." if len(edits) > 10 else ""))

        lines.append("\n---\n\n")

        with self.path.open("a") as f:
            f.write("\n".join(lines))

    def get_context_for_prompt(self, max_steps: int = 5) -> str:
        """Get recent history context for inclusion in evolver prompt.

        Returns formatted markdown snippet of recent steps for the evolver to read.
        """
        if not self.path.exists():
            return ""

        content = self.path.read_text()

        # Extract last N step sections (each starts with ## Step)
        sections = content.split("## Step ")
        if len(sections) <= 1:
            return ""

        # Take header + last max_steps sections
        header = sections[0]
        recent_sections = sections[-max_steps:]
        recent = "## Step ".join(recent_sections)

        return f"{header}\n## Step {recent}".strip()


def get_code_diff_command(
    snapshots_dir: Path,
    from_sha: str,
    to_sha: str,
) -> str:
    """Generate git command to view code diff between two snapshots.

    Returns a shell command that the evolver agent can run to see exact code changes.
    """
    return (
        f"git --git-dir={snapshots_dir} diff {from_sha[:12]}..{to_sha[:12]}"
    )


def compute_step_diff_from_dirs(
    current_step_dir: Path,
    previous_step_dir: Path | None,
    env_name: str,
) -> StepDiff | None:
    """Helper to compute diff from step directories.

    Args:
        current_step_dir: Current step's directory (e.g., step_001/)
        previous_step_dir: Previous step's directory (e.g., step_000/)
        env_name: Environment name to look for evaluation_summary.json

    Returns:
        StepDiff if both evaluations exist, None otherwise
    """
    if previous_step_dir is None:
        return None

    current_summary = current_step_dir / env_name / "run" / "evaluation_summary.json"
    previous_summary = previous_step_dir / env_name / "run" / "evaluation_summary.json"

    current_stats = EvaluationStats.from_summary_json(current_summary)
    previous_stats = EvaluationStats.from_summary_json(previous_summary)

    if current_stats is None or previous_stats is None:
        return None

    return StepDiff.compute(current_stats, previous_stats)
