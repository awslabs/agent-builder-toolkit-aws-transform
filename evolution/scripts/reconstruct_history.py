# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct evolution_history.md for an existing run from its artifacts.

Drives the (fixed) EvolutionHistory + summarize_trace_for_traj code over the
already-present evaluation_summary.json and agent_trace.jsonl files, so the
rebuilt history is byte-for-byte what a corrected live run would have written.

Usage:
    python scripts/reconstruct_history.py <run_dir> <train_env> <validation_env>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from harness_evolver.evolution_history import (
    EvaluationStats,
    EvolutionHistory,
    StepDiff,
    compute_step_diff_from_dirs,
)
from harness_evolver.evolver.prompt import summarize_trace_for_traj


def _ordered_step_dirs(run_dir: Path) -> list[tuple[int, Path, bool]]:
    """Return (step_number, dir, is_final) in chronological order.

    A step is "final" if no evolution ran from it — either it lives in a
    dedicated ``final_eval`` dir, or it's a ``step_NNN`` dir with no
    ``agent_trace.jsonl`` (older runs stored the terminal eval this way).
    """
    out: list[tuple[int, Path, bool]] = []
    for d in sorted(run_dir.glob("step_*")):
        if d.is_dir():
            is_final = not (d / "agent_trace.jsonl").exists()
            out.append((int(d.name.split("_")[1]), d, is_final))
    final = run_dir / "final_eval"
    if final.is_dir():
        nxt = (out[-1][0] + 1) if out else 0
        out.append((nxt, final, True))
    return out


def _read_snapshot_shas(run_dir: Path) -> dict[int, str]:
    """Map step -> post_sha (code state after that step's evolution)."""
    shas: dict[int, str] = {}
    traj = run_dir / "trajectory.jsonl"
    if not traj.exists():
        return shas
    for line in traj.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        step = rec.get("step")
        post = rec.get("post_sha")
        if isinstance(step, int) and post:
            shas[step] = post
    return shas


def _stopped_early(run_dir: Path) -> tuple[bool, int | None]:
    traj = run_dir / "trajectory.jsonl"
    if not traj.exists():
        return False, None
    for line in traj.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("event") == "early_stopping":
            return True, rec.get("best_validation_step")
    return False, None


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1]).resolve()
    train_env = sys.argv[2]
    val_env = sys.argv[3]

    if not run_dir.is_dir():
        print(f"run_dir not found: {run_dir}")
        return 1

    history_path = run_dir / "evolution_history.md"
    # Start fresh so the reconstruction is deterministic.
    if history_path.exists():
        backup = history_path.with_suffix(".md.bak")
        backup.write_text(history_path.read_text())
        history_path.unlink()
        print(f"backed up old history -> {backup}")

    snapshots_dir = run_dir / "snapshots.git"
    history = EvolutionHistory(
        history_path,
        snapshots_dir=snapshots_dir if snapshots_dir.exists() else None,
    )

    shas = _read_snapshot_shas(run_dir)
    stopped, best_step = _stopped_early(run_dir)
    steps = _ordered_step_dirs(run_dir)

    for step, step_dir, is_final in steps:
        train_stats = EvaluationStats.from_summary_json(
            step_dir / train_env / "run" / "evaluation_summary.json"
        )
        if train_stats is None:
            print(f"step {step}: no train summary, skipping")
            continue
        val_stats = EvaluationStats.from_summary_json(
            step_dir / val_env / "run" / "evaluation_summary.json"
        )

        # Diff vs previous step dir (handles step_000.. and final_eval).
        prev_dir: Path | None = None
        if step > 0:
            cand = run_dir / f"step_{step - 1:03d}"
            prev_dir = cand if cand.is_dir() else None
        diff: StepDiff | None = None
        if prev_dir is not None:
            diff = compute_step_diff_from_dirs(step_dir, prev_dir, train_env)

        metadata: dict = {}
        if is_final:
            metadata["final_eval"] = True
        if stopped and is_final:
            metadata["early_stopping_triggered"] = True
            metadata["best_validation_step"] = best_step

        history.record_evaluation(
            step=step,
            train_stats=train_stats,
            validation_stats=val_stats,
            diff=diff,
            metadata=metadata or None,
            snapshot_sha=shas.get(step),
        )

        # Evolution output only exists for non-final steps that actually ran.
        trace = step_dir / "agent_trace.jsonl"
        if not is_final and trace.exists():
            summary = summarize_trace_for_traj(trace)
            changes_summary = summary.get("summary", "")
            if not changes_summary:
                changes_summary = (
                    f"Modified {len(summary['edits'])} file(s)"
                    if summary.get("edits")
                    else "(no summary provided)"
                )
            history.record_evolution(
                step=step,
                changes_summary=changes_summary,
                edits=summary.get("edits"),
            )

    print(f"reconstructed -> {history_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
