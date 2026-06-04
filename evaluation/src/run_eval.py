#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repo-specific wiring for evaluating the AWS Transform agent-builder.

Builds the unified :class:`eval_runner.config.EvalConfig` for this repo:

- ``execution_config`` (an :class:`ExecutionConfig`) points the ACP engine at the
  agent under test (``agent_under_test/`` = AGENT.md + mcp.json) and the curated
  scenarios in ``test_samples/``.
- ``metrics`` selects the scoring metrics the ``EvaluationEngine`` applies:
  ``assertion_pass_rate`` (deterministic) + ``llm_judge`` (LLM-as-judge).

The CLI (``list`` / ``run`` / ``report`` / ``clean``) is provided by
:func:`eval_runner.cli.main`.

Usage::

    python src/run_eval.py list
    python src/run_eval.py run --scenario onboarding-intermediate --report

or via the installed console script::

    agent-builder-eval list

``run`` drives a live multi-turn conversation and requires the ACP driver binary
(``kiro-cli``) on PATH plus model access. ``list`` works offline.
"""

from __future__ import annotations

from pathlib import Path

from eval_runner.cli import main
from eval_runner.config import EvalConfig, ExecutionConfig

# run_eval.py lives in src/; the repo's data dirs (agent_under_test/, test_samples/)
# sit at the evaluation root one level up.
EVAL_DIR = Path(__file__).resolve().parent.parent


def get_execution_config() -> ExecutionConfig:
    """Build the ExecutionConfig (agent under test + ACP driver)."""
    return ExecutionConfig(
        agent_name="aws-transform-agent-builder",
        # Agent under test: AGENT.md + mcp.json pointing at the agent-builder MCP server.
        agent_dir=EVAL_DIR / "agent_under_test",
        # Curated eval scenarios (the test samples). Schema validation falls back
        # to the bundled eval-schema.json.
        evals_dir=EVAL_DIR / "test_samples",
        cli_binary_name="agent-builder-mcp",
        report_title="AWS Transform Agent Builder",
        # ACP driver binary. Defaults to "agent-cli"; this repo's environment ships
        # "kiro-cli" (ACP-compatible), so drive the agents with it.
        acp_binary="kiro-cli",
    )


def get_config() -> EvalConfig:
    """Build the unified eval_runner EvalConfig for this repo.

    Wraps the execution config and selects the scoring metrics applied by the
    ``EvaluationEngine`` (which the CLI ``run`` routes through).
    """
    return EvalConfig(
        test_dir=EVAL_DIR / "test_samples",
        metrics=["assertion_pass_rate", "llm_judge"],
        execution_config=get_execution_config(),
    )


def entry_point() -> None:
    """Zero-arg console-script entry point (``agent-builder-eval``)."""
    main(get_config())


if __name__ == "__main__":
    entry_point()
