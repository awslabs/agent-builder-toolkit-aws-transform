#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Simple evaluation wrapper for the AWS Transform agent-builder agent.

Runs a slice of the eval scenarios in evaluation/test_samples/ against an agent
under test (AGENT.md + mcp.json) using the in-repo evaluation framework
(eval_runner), and reports assertion pass rates. The agent is driven live over
ACP (the kiro-cli driver), so a run requires the ACP driver binary on PATH plus
Bedrock model access.

Usage:
    python scripts/run_agent_builder_evaluation.py --agent-dir <path> --test-slice 0:10 --output-dir <path>
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

# Repo layout. This file lives at evolution/scripts/run_agent_builder_evaluation.py, so the
# repo root is two levels up and the evaluation framework sits beside evolution/.
# Defaults are repo-relative (portable); override via env vars if needed.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_ROOT = Path(os.environ.get("AGENT_BUILDER_EVAL_ROOT", _REPO_ROOT / "evaluation"))

# Add the in-repo evaluation framework (eval_runner) to path.
EVAL_FRAMEWORK_DIR = Path(os.environ.get("AGENT_BUILDER_EVAL_FRAMEWORK_DIR", _EVAL_ROOT / "src"))
sys.path.insert(0, str(EVAL_FRAMEWORK_DIR))

# Imported after the sys.path insert above; E402 is intentional here.
from eval_runner.config import ExecutionConfig  # noqa: E402
from eval_runner.execution.loader import load_scenarios  # noqa: E402
from eval_runner.execution.runner import EvalCase, EvalOrchestrator  # noqa: E402
from eval_runner.models import AssertionResultStatus  # noqa: E402

# Agent-under-test wiring, mirroring evaluation/src/run_eval.py.
AGENT_NAME = "aws-transform-agent-builder"
CLI_BINARY_NAME = "agent-builder-mcp"
ACP_BINARY = os.environ.get("AGENT_BUILDER_ACP_BINARY", "kiro-cli")
AGENT_MODEL = os.environ.get("AGENT_BUILDER_AGENT_MODEL", "claude-opus-4.6")

# Default scenario directory (the test samples).
DEFAULT_TEST_DATA_DIR = Path(os.environ.get("AGENT_BUILDER_TEST_DATA_DIR", _EVAL_ROOT / "test_samples"))


def load_scenario_slice(test_data_dir: Path, test_slice: str) -> List[EvalCase]:
    """Load eval scenarios from a directory, then take the given slice.

    load_scenarios returns scenarios sorted by id (schema validation falls back
    to the framework's bundled eval-schema.json), so slicing is stable.
    """
    if ":" in test_slice:
        start, end = map(int, test_slice.split(":"))
    else:
        start = int(test_slice)
        end = start + 1

    scenarios = load_scenarios(test_data_dir)
    return scenarios[start:end]


def main():
    parser = argparse.ArgumentParser(description="Run AWS Transform agent-builder Evaluation")
    parser.add_argument(
        "--agent-dir",
        required=True,
        help="Path to the agent under test (AGENT.md + mcp.json)",
    )
    parser.add_argument("--test-data-dir", default=str(DEFAULT_TEST_DATA_DIR))
    parser.add_argument("--test-slice", default="0:10", help="Scenario slice (e.g., 0:10)")
    parser.add_argument("--output-dir", required=True, help="Output directory for results")

    args = parser.parse_args()

    agent_dir = Path(args.agent_dir)
    test_data_dir = Path(args.test_data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load scenarios
    print(f"Loading scenarios from {test_data_dir}, slice {args.test_slice}")
    scenarios = load_scenario_slice(test_data_dir, args.test_slice)
    print(f"Loaded {len(scenarios)} scenario(s)")

    if not scenarios:
        print(f"No scenarios found in slice {args.test_slice}.")
        return 1

    # Drive the agent under test over ACP.
    print(f"Initializing agent under test from {agent_dir}")
    exec_config = ExecutionConfig(
        agent_name=AGENT_NAME,
        agent_dir=agent_dir,
        agent_model=AGENT_MODEL,
        evals_dir=test_data_dir,
        cli_binary_name=CLI_BINARY_NAME,
        acp_binary=ACP_BINARY,
        report_title="AWS Transform agent-builder Evaluation",
    )

    orchestrator = EvalOrchestrator(
        config=exec_config,
        cwd=str(output_dir / "workspace"),
        results_dir=str(output_dir / "results"),
        verbose=True,
    )

    # Run evaluation
    print(f"Running evaluation on {len(scenarios)} scenario(s)")
    total_assertions = 0
    passed_assertions = 0
    test_summaries = []

    for scenario in scenarios:
        print(f"  Running scenario: {scenario.id}")
        grade = orchestrator.run_eval(
            scenario=scenario,
            workspace_cwd=str(output_dir / "workspace" / scenario.id),
        )

        test_assertions = len(grade.assertions)
        test_passed = sum(
            1 for a in grade.assertions if a.result == AssertionResultStatus.PASS
        )

        total_assertions += test_assertions
        passed_assertions += test_passed

        test_summaries.append({
            "test_id": scenario.id,
            "assertions_total": test_assertions,
            "assertions_passed": test_passed,
            "pass_rate": test_passed / test_assertions if test_assertions > 0 else 0.0,
        })

    overall_pass_rate = passed_assertions / total_assertions if total_assertions > 0 else 0.0

    # Write summary
    summary = {
        "test_slice": args.test_slice,
        "total_tests": len(scenarios),
        "total_assertions": total_assertions,
        "passed_assertions": passed_assertions,
        "overall_pass_rate": overall_pass_rate,
        "test_summaries": test_summaries,
    }

    summary_file = output_dir / "evaluation_summary.json"
    with summary_file.open("w") as f:
        json.dump(summary, f, indent=2)

    print("\nEvaluation Summary:")
    print(f"  Scenarios run: {len(scenarios)}")
    print(f"  Total assertions: {total_assertions}")
    print(f"  Passed assertions: {passed_assertions}")
    print(f"  Overall pass rate: {overall_pass_rate:.2%}")
    print(f"\nResults saved to: {output_dir}")

    return 0 if overall_pass_rate > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
