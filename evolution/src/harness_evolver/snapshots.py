# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Git-backed snapshot/rollback for a target directory."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
    )


class TargetSnapshots:
    """Git-backed snapshot ledger for a single target directory.

    The git metadata lives at `ledger_dir` (default: target_dir + ".git_ledger"),
    separate from the target directory itself so the target remains clean.
    """

    def __init__(self, target_dir: Path, ledger_dir: Path | None = None):
        self.target_dir = Path(target_dir).resolve()
        if not self.target_dir.exists():
            raise FileNotFoundError(self.target_dir)
        self.ledger_dir = Path(
            ledger_dir if ledger_dir is not None else str(self.target_dir) + ".git_ledger"
        ).resolve()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        cmd = [
            "git",
            f"--git-dir={self.ledger_dir}",
            f"--work-tree={self.target_dir}",
            *args,
        ]
        return _run(cmd, check=check)

    def _ensure_init(self) -> None:
        if not self.ledger_dir.exists():
            self.ledger_dir.mkdir(parents=True, exist_ok=True)
            _run(["git", "init", "--quiet", "--bare", str(self.ledger_dir)])
            self._git("config", "user.email", "agent-evolve@local")
            self._git("config", "user.name", "agent-evolve")
            self._git("config", "commit.gpgsign", "false")

    def init(self, label: str = "baseline") -> str:
        """Initialize (if needed) and take the first snapshot. Returns sha."""
        self._ensure_init()
        return self.snapshot(label)

    def snapshot(self, label: str) -> str:
        """Commit the current state of target_dir. Returns the commit sha."""
        self._ensure_init()
        self._git("add", "-A")
        self._git("commit", "--allow-empty", "-m", label, "--quiet")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def head(self) -> str:
        """Sha of the most recent snapshot, or '' if none yet."""
        if not self.ledger_dir.exists():
            return ""
        res = self._git("rev-parse", "HEAD", check=False)
        return res.stdout.strip() if res.returncode == 0 else ""

    def rollback(self, ref: str, *, save_branch_prefix: str = "archived") -> str | None:
        """Restore target_dir to the state captured at `ref`.

        Archives the abandoned timeline as a branch if HEAD is not an
        ancestor of `ref`. Returns the saved branch name or None.
        """
        self._ensure_init()

        saved_branch: str | None = None
        current_head = self.head()
        if current_head:
            ancestor = self._git(
                "merge-base", "--is-ancestor", current_head, ref, check=False
            )
            is_ancestor = ancestor.returncode == 0
            if not is_ancestor and current_head != self.resolve(ref):
                saved_branch = f"{save_branch_prefix}/{current_head[:12]}"
                self._git("branch", "-f", saved_branch, current_head)

        self._git("read-tree", "-u", "--reset", ref)
        self._git("update-ref", "HEAD", ref)
        self._git("clean", "-fdx")
        return saved_branch

    def diff(self, ref_a: str, ref_b: str) -> str:
        """Unified diff between two snapshots."""
        self._ensure_init()
        return self._git("diff", ref_a, ref_b).stdout

    def resolve(self, label_or_sha: str) -> str:
        """Resolve a label or sha to a full sha."""
        return self._git("rev-parse", label_or_sha).stdout.strip()
