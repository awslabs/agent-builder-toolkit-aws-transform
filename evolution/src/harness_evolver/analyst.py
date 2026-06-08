# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query


log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an analyst of agent behavior.

You will be given:
- a goal document describing what success looks like,
- an artifacts directory containing the evidence (trajectories, logs,
  metrics, raw outputs — task-specific),
- a target source directory (the agent's source code that produced the
  artifacts), read-only, available for understanding mechanism.

Your current working directory is your output directory. Write your
final report to `report.md` in the cwd. You may also write supporting
files (tables, notes, derived data) into the cwd if helpful, but the
primary deliverable is `report.md`.

Your job: inspect the artifacts and diagnose root causes — the specific
mechanisms by which failures occurred — with citations to concrete
evidence (file paths, instance IDs, log lines, exit statuses). When
useful for understanding why the agent produced a given outcome, Read
relevant files in the target source. Stop at the diagnosis. Explain
what happened and why it produced the wrong outcome.

The report must include:
1. A short structured summary block at the top (fenced as ```summary ...```)
   with any key metrics, pass/fail counts, or scalars you judge useful for
   downstream comparison. Include whatever is relevant. If no numerical signal
   is available, say so.
2. Qualitative diagnosis: for each notable failure or pattern, describe
   the mechanism (what the system did, why that produced the wrong
   outcome) and cite the evidence. Group by mechanism when multiple
   instances share a root cause. Note also what worked, with evidence.

Use the Read, Glob, and Grep tools to navigate the artifacts and target
source as much as you need. Write `report.md` with the Write tool. When
the report is written, stop."""


MAX_ATTEMPTS = 3


async def analyze(
    artifacts_dir: Path,
    goal: str,
    output_dir: Path,
    target_dir: Path | None = None,
) -> tuple[str, Path]:
    """Run the analyst agent and write a diagnostic report.

    The agent's cwd is `output_dir`; it writes `report.md` (and any
    supporting files) there. Returns (report_text, report_path).

    Retries up to MAX_ATTEMPTS times if the SDK call raises or the agent
    finishes without producing report.md.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "report.md"

    target_line = (
        f"  {Path(target_dir).resolve()}" if target_dir else "  (none)"
    )

    prompt = (
        f"Goal:\n{goal}\n\n"
        f"Artifacts directory (read-only — read evidence from here):\n"
        f"  {artifacts_dir}\n"
        f"Target source directory (read-only — read for mechanism understanding):\n"
        f"{target_line}\n\n"
        "Your cwd is your output directory. Write your report to "
        "`report.md` in the cwd. Inspect the artifacts and write the "
        "report."
    )

    options = ClaudeAgentOptions(
        cwd=str(output_dir),
        allowed_tools=["Read", "Glob", "Grep", "Write"],
        permission_mode="acceptEdits",
        system_prompt=SYSTEM_PROMPT,
    )

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log.info("analyst: attempt %d/%d", attempt, MAX_ATTEMPTS)
        try:
            async for _ in query(prompt=prompt, options=options):
                pass
        except Exception as e:
            last_err = e
            log.warning("analyst: attempt %d raised %r", attempt, e)
        if report_path.exists():
            return report_path.read_text(), report_path
        log.warning("analyst: attempt %d finished without writing report", attempt)

    raise RuntimeError(
        f"Analyst did not produce a report at {report_path} after "
        f"{MAX_ATTEMPTS} attempts. "
        f"Last error: {last_err!r}"
    )
