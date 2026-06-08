# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate a PR-style change review for a completed evolution run.

During an evolution run, the snapshots.git ledger's work-tree IS the env's
`target_dir` — the source agent directory being evolved (e.g. the agent under
test: AGENT.md + mcp.json). Every step is recorded in trajectory.jsonl
with a `pre_sha`/`post_sha` pair, so a plain `git diff pre post` against the
ledger is exactly the diff of the changed *source files* for that step.

This script turns those snapshots into a single markdown review document:
one section per step (changed files + diff, pre -> post), plus a cumulative
baseline -> final diff for the whole run — so you no longer have to assemble
the per-step diffs by hand.

Usage:
    python scripts/generate_change_review.py <run_env_dir> [-o OUTPUT.md] [--context N]

    <run_env_dir>  Directory containing trajectory.jsonl and snapshots.git
                   (e.g. runs/agent_builder_full_demo/agent_builder_train).
    -o / --output  Where to write the review (default: <run_env_dir>/change_review.md).
    --context      Unified-diff context lines (default: 3). Use 0 for tight diffs.

Read-only: this script never modifies the ledger, the target dir, or any
existing code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _git(git_dir: Path, *args: str) -> str:
    """Run a read-only git command against the bare snapshot ledger."""
    res = subprocess.run(
        ["git", f"--git-dir={git_dir}", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "?"


def _load_trajectory(traj_path: Path) -> list[dict]:
    """Parse trajectory.jsonl into a list of records (skipping bad lines)."""
    records: list[dict] = []
    for line in traj_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _step_records(records: list[dict]) -> list[dict]:
    """Evolution-step records (integer `step` with a post_sha), chronological."""
    steps = [
        r for r in records
        if isinstance(r.get("step"), int) and r.get("post_sha")
    ]
    steps.sort(key=lambda r: r["step"])
    return steps


def _baseline_sha(records: list[dict]) -> str | None:
    for r in records:
        if r.get("event") == "baseline" and r.get("baseline_sha"):
            return r["baseline_sha"]
    for r in records:  # fallback: any record carrying baseline_sha
        if r.get("baseline_sha"):
            return r["baseline_sha"]
    return None


def _target_dir(records: list[dict]) -> str | None:
    for r in records:
        if r.get("target_dir"):
            return r["target_dir"]
    return None


def _early_stop(records: list[dict]) -> dict | None:
    for r in records:
        if r.get("event") == "early_stopping":
            return r
    return None


def _render_step(git_dir: Path, rec: dict, context: int) -> str:
    """Render one evolution step as a PR-review section."""
    step = rec["step"]
    pre, post = rec.get("pre_sha"), rec["post_sha"]
    rationale = (rec.get("rationale") or "").strip()
    edits = rec.get("edits") or []

    stat = _git(git_dir, "diff", "--stat", pre, post).strip()
    diff = _git(git_dir, "diff", f"-U{context}", pre, post)

    out = [f"## Step {step}  (`{_short(pre)}` → `{_short(post)}`)\n"]

    if not diff.strip():
        out.append("_No file changes in this step (candidate produced no net edit)._\n")
    else:
        if edits:
            names = [Path(e).name for e in edits]
            out.append(f"**Files modified:** {', '.join(names)}\n")
        out.append("**Changed files:**\n")
        out.append("```\n" + stat + "\n```\n")

    if rationale:
        out.append("<details><summary>Evolver rationale</summary>\n")
        out.append(f"\n{rationale}\n\n</details>\n")

    if diff.strip():
        out.append("**Diff:**\n")
        out.append("```diff\n" + diff.rstrip("\n") + "\n```\n")

    return "\n".join(out)


def generate_review(run_env_dir: Path, output: Path, context: int = 3) -> Path:
    run_env_dir = run_env_dir.resolve()
    traj_path = run_env_dir / "trajectory.jsonl"
    git_dir = run_env_dir / "snapshots.git"

    if not traj_path.exists():
        sys.exit(f"error: {traj_path} not found")
    if not git_dir.exists():
        sys.exit(f"error: {git_dir} not found")

    records = _load_trajectory(traj_path)
    steps = _step_records(records)
    baseline = _baseline_sha(records)
    target = _target_dir(records)
    early = _early_stop(records)

    if not steps:
        sys.exit("error: no evolution-step records found in trajectory.jsonl")

    final_post = steps[-1]["post_sha"]

    lines: list[str] = [f"# Change Review — {run_env_dir.name}\n"]
    if target:
        lines.append(f"Source under review: `{target}`")
    lines.append(f"Snapshot ledger: `{git_dir}`")
    lines.append(
        f"Baseline: `{_short(baseline)}`  ·  Final: `{_short(final_post)}`  ·  "
        f"Steps: {len(steps)}\n"
    )

    if early:
        lines.append(
            f"> ⚠️ Early stopping triggered at step {early.get('step', '?')} "
            f"(best validation step: {early.get('best_validation_step', '?')}).\n"
        )

    # Per-step sections.
    for rec in steps:
        lines.append(_render_step(git_dir, rec, context))

    # Cumulative diff: baseline -> final.
    if baseline:
        cum_stat = _git(git_dir, "diff", "--stat", baseline, final_post).strip()
        cum_diff = _git(git_dir, "diff", f"-U{context}", baseline, final_post)
        lines.append(
            f"## Cumulative  (baseline `{_short(baseline)}` → final `{_short(final_post)}`)\n"
        )
        if cum_diff.strip():
            lines.append("**Net changed files:**\n")
            lines.append("```\n" + cum_stat + "\n```\n")
            lines.append("**Net diff:**\n")
            lines.append("```diff\n" + cum_diff.rstrip("\n") + "\n```\n")
        else:
            lines.append("_No net change from baseline to final._\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    return output


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("run_env_dir", type=Path,
                   help="Run env dir containing trajectory.jsonl and snapshots.git")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output markdown path (default: <run_env_dir>/change_review.md)")
    p.add_argument("--context", type=int, default=3,
                   help="Unified-diff context lines (default: 3)")
    args = p.parse_args()

    output = args.output or (args.run_env_dir / "change_review.md")
    written = generate_review(args.run_env_dir, output, context=args.context)
    print(f"Wrote change review: {written}")


if __name__ == "__main__":
    main()
