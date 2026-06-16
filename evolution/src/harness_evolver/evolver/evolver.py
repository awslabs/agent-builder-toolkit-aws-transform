# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
)

from harness_evolver.analyst import analyze
from harness_evolver.confinement import confinement_hooks
from harness_evolver.environment import Environment
from harness_evolver.evolution_history import (
    EvaluationStats,
    EvolutionHistory,
    compute_step_diff_from_dirs,
)
from harness_evolver.snapshots import TargetSnapshots
from harness_evolver.trajectory import Trajectory, serialize_message

from .prompt import (
    SYSTEM_PROMPT,
    build_edit_prompt,
    summarize_trace_for_traj,
)

log = logging.getLogger(__name__)


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


async def _run_env_and_evaluate(
    env: Environment,
    step_dir: Path,
) -> tuple[str, str]:
    """Run one env, evaluate its run, return (env.name, report_text).

    Layout under env_dir:
        run/              — env artifacts written by env.run
        analyst_output/   — analyst's outputs (cwd); contains report.md
    """
    env_dir = step_dir / env.name
    run_dir_ = env_dir / "run"
    analyst_output_dir = env_dir / "analyst_output"
    run_dir_.mkdir(parents=True, exist_ok=True)
    analyst_output_dir.mkdir(parents=True, exist_ok=True)

    log.info("env %s: running", env.name)
    result = env.run(env.target_dir, run_dir_)
    await _maybe_await(result)
    log.info("env %s: run complete, analyzing artifacts", env.name)

    report, report_path = await analyze(
        artifacts_dir=run_dir_,
        goal=env.goal,
        output_dir=analyst_output_dir,
        target_dir=env.target_dir,
    )
    log.info("env %s: report written to %s", env.name, report_path)
    return env.name, report


# Cap on the inner agent's conversation turns per evolution step. The --budget
# flag bounds the *outer* evolution loop (number of steps); under acceptEdits a
# single step would otherwise loop unbounded. One step is "read reports, make a
# few edits, summarize" — generous but finite.
_MAX_TURNS_PER_STEP = 60


async def _run_evolver_step(
    target_dir: Path,
    edit_prompt: str,
    trace_path: Path,
) -> None:
    """Invoke the evolver agent with edit tools confined to target_dir.

    Confinement is layered:
      - ``tools`` pins the available tool set, so Bash/NotebookEdit are not even
        exposed to the model (``allowed_tools`` only auto-approves; it does not
        restrict availability).
      - a ``PreToolUse`` hook gates every tool call and denies any write whose
        path escapes target_dir (and default-denies unrecognized tools). The
        hook — not ``can_use_tool`` — is used because ``acceptEdits``
        auto-approves Write/Edit before ``can_use_tool`` would ever see them.
    """
    options = ClaudeAgentOptions(
        cwd=str(target_dir),
        tools=["Read", "Glob", "Grep", "Write", "Edit"],
        allowed_tools=["Read", "Glob", "Grep", "Write", "Edit"],
        permission_mode="acceptEdits",
        system_prompt=SYSTEM_PROMPT,
        hooks=confinement_hooks(target_dir),
        max_turns=_MAX_TURNS_PER_STEP,
    )

    # Use ClaudeSDKClient (not the one-shot query()) because the PreToolUse hook
    # sends its allow/deny verdict back to the CLI *over stdin*. ClaudeSDKClient
    # holds the session (and stdin) open until disconnect, so the hook can
    # respond throughout the turn.
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("w") as f:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(edit_prompt)
            async for msg in client.receive_response():
                try:
                    f.write(json.dumps(serialize_message(msg), default=str) + "\n")
                    f.flush()
                except Exception as e:
                    f.write(json.dumps({"type": "SERIALIZATION_ERROR", "error": repr(e)}) + "\n")


async def run(
    train: Environment,
    validation: Environment | None,
    budget: int,
    run_dir: Path,
    early_stopping_patience: int = 0,
    early_stopping_min_delta: float = 0.01,
) -> None:
    """Evolve loop: iteratively improve a target agent via feedback.

    For each step:
      1. Run train (and validation if provided) against the target_dir.
      2. Analyze artifacts into a report.
      3. Invoke the evolver agent with the reports + recent trajectory.
      4. Log a step record to trajectory.jsonl.

    After `budget` steps, runs one final measurement-only pass.

    Args:
        early_stopping_patience: Stop if validation doesn't improve for N steps.
                                0 = disabled (default)
                                2 = recommended
        early_stopping_min_delta: Minimum improvement to reset patience (default 1%)
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    target_dir = train.target_dir
    log.info(
        "evolve start: target=%s budget=%d run_dir=%s early_stopping=%s",
        target_dir, budget, run_dir,
        f"patience={early_stopping_patience}" if early_stopping_patience > 0 else "disabled"
    )

    snapshots = TargetSnapshots(
        target_dir=target_dir,
        ledger_dir=run_dir / "snapshots.git",
    )
    baseline_sha = snapshots.init("baseline")

    traj = Trajectory(run_dir / "trajectory.jsonl")
    traj.append(
        event="baseline",
        target_dir=str(target_dir),
        baseline_sha=baseline_sha,
    )

    # Initialize evolution history tracker with snapshots directory
    history = EvolutionHistory(
        path=run_dir / "evolution_history.md",
        snapshots_dir=run_dir / "snapshots.git",
    )

    train_reports_dir = run_dir / "reports" / train.name
    train_reports_dir.mkdir(parents=True, exist_ok=True)
    validation_reports_dir: Path | None = None
    if validation is not None:
        validation_reports_dir = run_dir / "reports" / validation.name
        validation_reports_dir.mkdir(parents=True, exist_ok=True)

    # Early stopping state
    best_validation_score = -1.0
    best_validation_step = -1
    patience_counter = 0
    stopped_early = False

    for step in range(budget + 1):
        is_final = step == budget or stopped_early
        step_dir = run_dir / (f"step_{step:03d}" if not is_final else "final_eval")
        step_dir.mkdir(parents=True, exist_ok=True)
        log.info("=== %s ===", "final_eval" if is_final else f"step {step:03d}")

        # Run train env
        train_name, train_report = await _run_env_and_evaluate(train, step_dir)
        report_name = "final" if is_final else f"step_{step:03d}"
        train_report_path = train_reports_dir / f"{report_name}.md"
        train_report_path.write_text(train_report)

        # Run validation env (if provided)
        validation_name: str | None = None
        validation_report_path: Path | None = None
        current_validation_score = -1.0

        if validation is not None:
            validation_name, validation_report = await _run_env_and_evaluate(
                validation, step_dir
            )
            validation_report_path = validation_reports_dir / f"{report_name}.md"
            validation_report_path.write_text(validation_report)

            # Parse validation score for early stopping
            if not is_final:
                summary_file = step_dir / validation.name / "run" / "evaluation_summary.json"
                if summary_file.exists():
                    try:
                        with summary_file.open() as f:
                            summary = json.load(f)
                            current_validation_score = summary.get("assertion_pass_rate", 0.0)
                    except Exception as e:
                        log.warning(f"Could not parse validation score: {e}")

        # Early stopping check (only if validation available and not final)
        if (validation is not None
            and not is_final
            and early_stopping_patience > 0
            and current_validation_score >= 0):

            improvement = current_validation_score - best_validation_score

            if improvement > early_stopping_min_delta:
                # Significant improvement - reset patience
                best_validation_score = current_validation_score
                best_validation_step = step
                patience_counter = 0
                log.info(
                    "step %03d: validation improved by %.2f%% (%.1f%% -> %.1f%%), patience reset",
                    step, improvement * 100,
                    (best_validation_score - improvement) * 100,
                    best_validation_score * 100
                )
            else:
                # No significant improvement - increment patience
                patience_counter += 1
                log.info(
                    "step %03d: validation did not improve (%.1f%% vs best %.1f%%), "
                    "patience %d/%d",
                    step, current_validation_score * 100, best_validation_score * 100,
                    patience_counter, early_stopping_patience
                )

                if patience_counter >= early_stopping_patience:
                    log.info(
                        "step %03d: EARLY STOPPING triggered "
                        "(no improvement for %d steps, best was step %d at %.1f%%)",
                        step, early_stopping_patience, best_validation_step,
                        best_validation_score * 100
                    )
                    stopped_early = True
                    is_final = True

                    # Record early stopping event
                    traj.append(
                        event="early_stopping",
                        step=step,
                        best_validation_step=best_validation_step,
                        best_validation_score=best_validation_score,
                        patience=early_stopping_patience,
                    )

        # Record evaluation results to evolution history. Done for every step
        # including the final eval, so the last data point (and the reason the
        # run ended) is never silently dropped.
        train_stats = EvaluationStats.from_summary_json(
            step_dir / train.name / "run" / "evaluation_summary.json"
        )
        validation_stats = None
        if validation is not None:
            validation_stats = EvaluationStats.from_summary_json(
                step_dir / validation.name / "run" / "evaluation_summary.json"
            )

        # Compute diff from previous step
        diff = None
        if step > 0:
            prev_step_dir = run_dir / f"step_{step - 1:03d}"
            diff = compute_step_diff_from_dirs(step_dir, prev_step_dir, train.name)

        metadata = {}
        if is_final:
            metadata["final_eval"] = True
        if stopped_early:
            metadata["early_stopping_triggered"] = True
            metadata["best_validation_step"] = best_validation_step

        if train_stats:
            # Get current snapshot SHA for code reference
            current_sha = snapshots.head()

            history.record_evaluation(
                step=step,
                train_stats=train_stats,
                validation_stats=validation_stats,
                diff=diff,
                metadata=metadata if metadata else None,
                snapshot_sha=current_sha if current_sha else None,
            )

        if is_final:
            traj.append(
                event="final_eval",
                target_dir=str(target_dir),
                train_env=train_name,
                validation_env=validation_name,
                step_dir=str(step_dir),
                baseline_sha=baseline_sha,
                stopped_early=stopped_early,
            )
            break

        # Holdout not shown on step 0 — no prior edit to validate yet.
        shown_validation: list[tuple[str, Path, Path]] = (
            [(validation_name, validation_report_path, validation_reports_dir)]
            if (
                validation is not None
                and step > 0
                and validation_report_path is not None
                and validation_reports_dir is not None
            )
            else []
        )

        # Get evolution history context (last 5 steps)
        history_context = history.get_context_for_prompt(max_steps=5)

        prompt_text = build_edit_prompt(
            target_dir=target_dir,
            train_reports=[(train_name, train_report_path, train_reports_dir)],
            validation_reports=shown_validation,
            recent_trajectory=traj.recent(k=5),
            step=step,
            history_context=history_context if history_context else None,
        )
        (step_dir / "prompt.md").write_text(prompt_text)

        pre_sha = snapshots.snapshot(f"pre_step_{step:03d}")

        log.info("step %03d: invoking evolver agent", step)
        trace_path = step_dir / "agent_trace.jsonl"
        await _run_evolver_step(target_dir, prompt_text, trace_path)

        post_sha = snapshots.snapshot(f"post_step_{step:03d}")

        summary = summarize_trace_for_traj(trace_path)
        log.info(
            "step %03d: evolver done, edits=%s",
            step, summary["edits"] or "[none]",
        )
        traj.append(
            step=step,
            target_dir=str(target_dir),
            train_env=train_name,
            validation_env=validation_name,
            validation_shown_to_evolver=(step != 0),
            rationale=summary["rationale"],
            summary=summary["summary"],
            edits=summary["edits"],
            tool_calls=summary["tool_calls"],
            trace_path=str(trace_path),
            step_dir=str(step_dir),
            pre_sha=pre_sha,
            post_sha=post_sha,
            baseline_sha=baseline_sha,
        )

        # Record evolution output to history (after evolution). The summary is
        # the agent's clean final answer; rationale is its raw thinking. Keep
        # them distinct so the history doesn't print the same text twice.
        changes_summary = summary.get("summary", "")
        if not changes_summary:
            changes_summary = (
                f"Modified {len(summary['edits'])} file(s)"
                if summary.get("edits")
                else "(no summary provided)"
            )

        # rationale (raw thinking) is intentionally omitted from the history:
        # the clean summary already explains the "why", and the raw reasoning
        # is preserved in the trajectory + agent_trace.jsonl.
        history.record_evolution(
            step=step,
            changes_summary=changes_summary,
            edits=summary.get("edits"),
        )
