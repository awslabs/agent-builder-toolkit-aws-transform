# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Round-trip tests for the git-backed snapshot ledger.

These pin the property the orchestrator's checkpoint restore relies on:
restoring a snapshot makes the work-tree byte-for-byte equal to that snapshot,
including *deleting* files that later snapshots added. A naive
``git checkout <sha> -- .`` does not do this (it only overwrites tracked paths),
which was the root cause of the "ships a tree no eval ever scored" bug.
"""

import tempfile
from pathlib import Path

from harness_evolver.snapshots import TargetSnapshots


def _tree_contents(d: Path) -> dict[str, str]:
    """Map of relative-path -> file contents for every file under d (excludes .git)."""
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            out[str(p.relative_to(d))] = p.read_text()
    return out


def test_snapshot_restore_round_trip_deletes_later_files():
    """snapshot -> mutate + add file -> restore must drop the added file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        target = tmp / "target"
        target.mkdir()
        (target / "AGENT.md").write_text("v0\n")

        snaps = TargetSnapshots(target_dir=target, ledger_dir=tmp / "snapshots.git")
        baseline = snaps.snapshot("pre_step_000")
        baseline_tree = _tree_contents(target)

        # Step edits AGENT.md and adds a brand-new file.
        (target / "AGENT.md").write_text("v1 — edited\n")
        (target / "extra.md").write_text("added in a later step\n")
        snaps.snapshot("post_step_000")

        assert (target / "extra.md").exists()
        assert (target / "AGENT.md").read_text() == "v1 — edited\n"

        # Restoring the baseline must fully reconstruct it: AGENT.md reverts AND
        # the later-added extra.md is removed.
        snaps.rollback(baseline)

        assert not (target / "extra.md").exists(), "rollback left a later-step file behind"
        assert _tree_contents(target) == baseline_tree


def test_resolve_label_to_sha():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        target = tmp / "target"
        target.mkdir()
        (target / "AGENT.md").write_text("hello\n")

        snaps = TargetSnapshots(target_dir=target, ledger_dir=tmp / "snapshots.git")
        sha = snaps.snapshot("baseline")

        assert snaps.resolve("HEAD") == sha
        assert snaps.head() == sha
