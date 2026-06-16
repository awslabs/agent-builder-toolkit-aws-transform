# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter for the ``evohistory`` verb — surface a run's ``evolution_history.md``.

An evolution run writes a human-readable ``evolution_history.md`` (cumulative
per-step results + decisions) into its run directory — e.g.
``runs/<run>/<train_env>/evolution_history.md``. This adapter locates that file
for a given run directory and returns its path + text, so the CLI can print it.

No evolver dependency is needed: it's a plain file read, with a recursive search
so callers can pass either the per-env dir (where the file lives) or a parent run
dir that contains it one level down.
"""

from __future__ import annotations

from pathlib import Path

HISTORY_FILENAME = "evolution_history.md"


def find_history(run_dir: Path) -> Path | None:
    """Locate ``evolution_history.md`` for a run.

    Checks ``run_dir`` itself first, then searches one level of subdirectories
    (the per-env dirs, e.g. ``agent_builder_train``). Returns the first match by
    sorted path, or None if not found.
    """
    run_dir = Path(run_dir)
    direct = run_dir / HISTORY_FILENAME
    if direct.is_file():
        return direct
    matches = sorted(run_dir.glob(f"*/{HISTORY_FILENAME}"))
    return matches[0] if matches else None


def get_history(run_dir: Path) -> tuple[str, Path]:
    """Return ``(text, path)`` for the run's evolution_history.md.

    Raises:
        FileNotFoundError: If no evolution_history.md is found under ``run_dir``.
    """
    path = find_history(run_dir)
    if path is None:
        raise FileNotFoundError(
            f"No {HISTORY_FILENAME} found under {Path(run_dir).resolve()} "
            f"(checked the dir itself and its immediate subdirectories)."
        )
    return path.read_text(), path
