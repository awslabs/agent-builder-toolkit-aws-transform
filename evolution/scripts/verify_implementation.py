#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify that Phases 2-4 are correctly implemented.

Usage:
    cd evolution
    python scripts/verify_implementation.py
"""

import sys
from pathlib import Path


def check_file(file_path: Path, checks: list[dict]) -> tuple[int, int]:
    """Check if specific strings/patterns exist in a file.

    Returns: (passed, total)
    """
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return 0, len(checks)

    content = file_path.read_text()
    passed = 0

    for check in checks:
        name = check["name"]
        pattern = check["pattern"]

        if pattern in content:
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name}")
            if check.get("hint"):
                print(f"    Hint: {check['hint']}")

    return passed, len(checks)


def main():
    base_dir = Path(__file__).parent.parent

    print("="*80)
    print("Verifying Phases 2-4 Implementation")
    print("="*80)

    total_passed = 0
    total_checks = 0

    # Phase 2: Early Stopping
    print("\n📋 Phase 2: Early Stopping")
    print("-" * 80)

    evolver_file = base_dir / "src" / "harness_evolver" / "evolver" / "evolver.py"
    evolver_checks = [
        {
            "name": "early_stopping_patience parameter added",
            "pattern": "early_stopping_patience: int = 0",
        },
        {
            "name": "early_stopping_min_delta parameter added",
            "pattern": "early_stopping_min_delta: float = 0.01",
        },
        {
            "name": "Early stopping state variables",
            "pattern": "best_validation_score = -1.0",
        },
        {
            "name": "Early stopping trigger logic",
            "pattern": "EARLY STOPPING triggered",
        },
        {
            "name": "stopped_early variable",
            "pattern": "stopped_early = False",
        },
    ]

    p, t = check_file(evolver_file, evolver_checks)
    total_passed += p
    total_checks += t

    orchestrator_file = base_dir / "src" / "harness_evolver" / "orchestrator.py"
    orchestrator_checks = [
        {
            "name": "run_evolve has early_stopping parameters",
            "pattern": "early_stopping_patience: int = 0",
        },
        {
            "name": "run_experiment has early_stopping parameters",
            "pattern": "early_stopping_patience: int = 0",
        },
        {
            "name": "Parameters passed to evolver.run",
            "pattern": "early_stopping_patience=early_stopping_patience",
        },
    ]

    p, t = check_file(orchestrator_file, orchestrator_checks)
    total_passed += p
    total_checks += t

    # Phase 3: Regularization
    print("\n📋 Phase 3: Regularization")
    print("-" * 80)

    prompt_file = base_dir / "src" / "harness_evolver" / "evolver" / "prompt.py"
    prompt_checks = [
        {
            "name": "Section 6 added to SYSTEM_PROMPT",
            "pattern": "6. **Prefer simplicity and avoid unnecessary complexity.**",
        },
        {
            "name": "Complexity Budget guideline",
            "pattern": "a) **Complexity Budget**:",
        },
        {
            "name": "Specificity vs Generalization",
            "pattern": "b) **Specificity vs Generalization Trade-off**:",
        },
        {
            "name": "Remove Before Adding guideline",
            "pattern": "c) **Remove Before Adding**:",
        },
        {
            "name": "Complexity-budget reminder (file-agnostic)",
            "pattern": "## Complexity budget",
        },
        {
            "name": "Enhanced validation framing",
            "pattern": "GENERALIZATION CHECK",
        },
    ]

    p, t = check_file(prompt_file, prompt_checks)
    total_passed += p
    total_checks += t

    # Phase 4: Better Data Split
    print("\n📋 Phase 4: Better Data Split")
    print("-" * 80)

    experiment_file = base_dir / "experiment" / "evolve_agent_builder.py"
    experiment_checks = [
        {
            "name": "Full config has early_stopping",
            "pattern": '"early_stopping": 3',
        },
        {
            "name": "Full train_slice set to 0:30",
            "pattern": '"train_slice": "0:30"',
        },
        {
            "name": "Full validation_slice set to 30:40",
            "pattern": '"validation_slice": "30:40"',
        },
        {
            "name": "Full test_slice set to 40:50",
            "pattern": '"test_slice": "40:50"',
        },
        {
            "name": "Early stopping passed to run_experiment",
            "pattern": 'early_stopping_patience=config.get("early_stopping", 0)',
        },
    ]

    p, t = check_file(experiment_file, experiment_checks)
    total_passed += p
    total_checks += t

    # Summary
    print("\n" + "="*80)
    print(f"VERIFICATION SUMMARY: {total_passed}/{total_checks} checks passed")
    print("="*80)

    if total_passed == total_checks:
        print("\n🎉 SUCCESS! All phases are correctly implemented.")
        print("\nNext steps:")
        print("  1. Run a quick test:")
        print("     PYTHONPATH=. python experiment/evolve_agent_builder.py")
        print("  2. Monitor with dashboard:")
        print("     bash scripts/start_dashboard.sh agent_builder_quick")
        print("  3. Verify results:")
        print("     python scripts/verify_model_selection.py")
        return 0
    else:
        print(f"\n⚠️  {total_checks - total_passed} checks failed.")
        print("\nPlease review the failed checks above and fix them.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
