# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""AWS Transform agent-builder agent environment wrapper.

Evolves the AWS Transform agent-builder agent under test (AGENT.md + mcp.json)
by running the repo's curated eval scenarios through the in-repo evaluation
framework (``evaluation/``) and measuring assertion pass rates.

Environment boundary:
    - EDITABLE (lives inside target_dir):
        evaluation/agent_under_test/
        ├── AGENT.md
        └── mcp.json
    - READ-ONLY (lives OUTSIDE target_dir):
        Eval scenarios in evaluation/test_samples/
        Evaluation framework (eval_runner) in evaluation/src/

The evaluation framework drives the agent under test live over ACP (the
``kiro-cli`` driver) and grades transcripts with an LLM judge, so a run requires
the ACP driver binary on PATH plus Bedrock model access.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
from pathlib import Path

from harness_evolver.environment import Environment

# Repo layout. This file lives at evolution/env_configs/agent_builder_env.py, so the
# repo root is two levels up and the evaluation framework sits beside evolution/.
# Defaults are repo-relative (portable); override via env vars if needed.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_ROOT = Path(os.environ.get("AGENT_BUILDER_EVAL_ROOT", _REPO_ROOT / "evaluation"))

# Add the in-repo evaluation framework (eval_runner) to path.
EVAL_FRAMEWORK_DIR = Path(
    os.environ.get("AGENT_BUILDER_EVAL_FRAMEWORK_DIR", _EVAL_ROOT / "src")
)
if str(EVAL_FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_FRAMEWORK_DIR))

from eval_runner.config import ExecutionConfig
from eval_runner.execution.loader import load_scenarios
from eval_runner.execution.runner import EvalOrchestrator
from eval_runner.models import AssertionResultStatus


# Agent-under-test wiring, mirroring evaluation/src/run_eval.py.
AGENT_NAME = "aws-transform-agent-builder"
CLI_BINARY_NAME = "agent-builder-mcp"
# This repo's environment ships kiro-cli (ACP-compatible) as the ACP driver.
ACP_BINARY = os.environ.get("AGENT_BUILDER_ACP_BINARY", "kiro-cli")
AGENT_MODEL = os.environ.get("AGENT_BUILDER_AGENT_MODEL", "claude-opus-4.6")


WORKER_GOAL = """Improve the AWS Transform agent-builder agent's assertion pass rate on the eval scenarios.

Success = higher assertion pass rate across the scenario set. When analyzing failure patterns, look for:
- Missing or incorrect instructions in AGENT.md that cause the agent to skip required tool calls
- Unclear guidance that leads to wrong tool usage
- Overly restrictive instructions that block legitimate actions
- Missing edge-case handling (e.g., environment limitations, error scenarios)
- Instructions that work for seen scenarios but don't generalize to unseen ones

Prefer interventions that:
1. Make tool-call requirements explicit and prominent (e.g., "MUST call keyword_search FIRST")
2. Provide clear examples and decision trees
3. Cover edge cases mentioned in scenario assertions
4. Are general across different user queries, not specific to individual scenarios
5. Balance between being prescriptive enough for reliability and flexible enough for novel scenarios
"""


# Target directory containing the agent files to evolve (AGENT.md + mcp.json).
AGENT_BUILDER_TARGET_DIR = Path(
    os.environ.get("AGENT_BUILDER_TARGET_DIR", _EVAL_ROOT / "agent_under_test")
)

# Eval scenario directory (the test samples).
TEST_DATA_DIR = Path(
    os.environ.get("AGENT_BUILDER_TEST_DATA_DIR", _EVAL_ROOT / "test_samples")
)


def make_env(
    name: str,
    test_slice: str = "0:10",
    n_concurrent: int = 1,
) -> Environment:
    """Build an Agent Builder Environment for the given test slice.

    Args:
        name: Short slug identifying this env (used in run paths)
        test_slice: e.g. "0:10" for first 10 tests, "10:20" for next 10
        n_concurrent: Number of parallel test executions (default 1 for stability)
    """

    def run(target_dir: Path, artifacts_dir: Path) -> None:
        """Run the eval scenarios against the agent files in target_dir.

        Drives the in-repo evaluation framework: ``target_dir`` is the evolver's
        editable copy of ``agent_under_test/`` (AGENT.md + mcp.json), so pointing
        ``ExecutionConfig.agent_dir`` at it is what makes the evolver's edits
        actually get evaluated.
        """
        target_dir = Path(target_dir)
        artifacts_dir = Path(artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        run_id = f"{name}_{uuid.uuid4().hex[:8]}"
        eval_log_path = artifacts_dir / "evaluation.log"

        # Parse slice spec
        if ":" in test_slice:
            start, end = map(int, test_slice.split(":"))
        else:
            start = int(test_slice)
            end = start + 1

        # Load scenarios from the test-sample directory (schema validation falls
        # back to the framework's bundled eval-schema.json) and take the slice.
        # load_scenarios returns scenarios sorted by id, so slicing is stable.
        all_scenarios = load_scenarios(TEST_DATA_DIR)
        scenario_subset = all_scenarios[start:end]

        if not scenario_subset:
            (artifacts_dir / "ERROR.txt").write_text(
                f"No scenarios found in slice {test_slice}. "
                f"Total scenarios in {TEST_DATA_DIR}: {len(all_scenarios)}\n"
            )
            return

        # Initialize results
        summary = {
            "run_id": run_id,
            "test_slice": test_slice,
            "total_tests": len(scenario_subset),
            "tests_run": 0,
            "total_assertions": 0,
            "assertions_passed": 0,
            "assertion_pass_rate": 0.0,
            "tests": [],
        }

        # Drive the agent under test (the evolver's editable copy) over ACP.
        exec_config = ExecutionConfig(
            agent_name=AGENT_NAME,
            agent_dir=target_dir,
            agent_model=AGENT_MODEL,
            evals_dir=TEST_DATA_DIR,
            cli_binary_name=CLI_BINARY_NAME,
            acp_binary=ACP_BINARY,
            report_title="AWS Transform agent-builder Evolution",
        )

        orchestrator = EvalOrchestrator(
            config=exec_config,
            cwd=str(artifacts_dir / "workspace"),
            results_dir=str(artifacts_dir / "results"),
            verbose=True,
        )

        # Run each scenario
        with eval_log_path.open("w") as log_f:
            log_f.write(f"Starting evaluation run {run_id}\n")
            log_f.write(f"Test slice: {test_slice} ({len(scenario_subset)} scenarios)\n")
            log_f.write(f"Agent directory: {target_dir}\n\n")

            for scenario in scenario_subset:
                try:
                    log_f.write(f"Running scenario: {scenario.id}\n")
                    log_f.flush()

                    # Run evaluation end-to-end (execute + LLM-judge grade).
                    grade = orchestrator.run_eval(
                        scenario=scenario,
                        workspace_cwd=str(artifacts_dir / "workspace" / scenario.id),
                    )

                    summary["tests_run"] += 1

                    # Count assertions
                    total_test_assertions = len(grade.assertions)
                    passed_test_assertions = sum(
                        1 for a in grade.assertions
                        if a.result == AssertionResultStatus.PASS
                    )

                    summary["total_assertions"] += total_test_assertions
                    summary["assertions_passed"] += passed_test_assertions

                    summary["tests"].append({
                        "test_id": scenario.id,
                        "assertions_total": total_test_assertions,
                        "assertions_passed": passed_test_assertions,
                        "passed": grade.passed,
                    })

                    log_f.write(f"  Result: {'PASS' if grade.passed else 'FAIL'} "
                              f"({passed_test_assertions}/{total_test_assertions} assertions)\n")

                    # Save individual scenario result
                    test_result_file = artifacts_dir / "results" / f"{scenario.id}.json"
                    test_result_file.parent.mkdir(parents=True, exist_ok=True)
                    with test_result_file.open("w") as f:
                        json.dump({
                            "test_id": scenario.id,
                            "passed": grade.passed,
                            "assertions": [
                                {
                                    "name": a.name,
                                    "result": a.result.value,
                                    "evidence": a.evidence,
                                }
                                for a in grade.assertions
                            ],
                            "token_usage": {
                                "input_tokens": grade.token_usage.input_tokens,
                                "output_tokens": grade.token_usage.output_tokens,
                            } if grade.token_usage else None,
                        }, f, indent=2)

                except Exception as e:
                    log_f.write(f"ERROR running scenario {scenario.id}: {e}\n")
                    import traceback
                    traceback.print_exc(file=log_f)
                    log_f.flush()

        # Calculate pass rate
        if summary["total_assertions"] > 0:
            summary["assertion_pass_rate"] = (
                summary["assertions_passed"] / summary["total_assertions"]
            )

        # Write summary
        summary_file = artifacts_dir / "evaluation_summary.json"
        with summary_file.open("w") as f:
            json.dump(summary, f, indent=2)

        # Write run ID for tracking
        (artifacts_dir / "run_id.txt").write_text(run_id + "\n")

    return Environment(
        target_dir=AGENT_BUILDER_TARGET_DIR,
        goal=WORKER_GOAL,
        run=run,
        name=name,
    )
