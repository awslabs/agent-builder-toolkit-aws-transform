#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify model selection logic on existing run without re-running training.

This script tests the model selection implementation by:
1. Reading existing validation results from a completed run
2. Identifying which checkpoint would have been selected
3. Showing what the test performance would have been with that checkpoint

Usage:
    cd evolution
    source .venv/bin/activate
    python scripts/verify_model_selection.py
"""

import json
import re
from pathlib import Path


def analyze_run(run_dir: Path):
    """Analyze a completed run and show what model selection would have chosen."""

    print(f"\n{'='*80}")
    print(f"Analyzing run: {run_dir}")
    print(f"{'='*80}\n")

    # Find train directory
    train_dir = run_dir / "agent_builder_train"
    if not train_dir.exists():
        print(f"Error: Could not find {train_dir}")
        return

    # Collect validation results from each step
    print("Validation Performance by Step:")
    print("-" * 80)

    results = []
    for step_dir in sorted(train_dir.glob("step_*")):
        step_match = re.search(r"step_(\d+)", step_dir.name)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Get validation results
        val_summary = step_dir / "agent_builder_validation" / "run" / "evaluation_summary.json"
        train_summary = step_dir / "agent_builder_train" / "run" / "evaluation_summary.json"

        if not val_summary.exists() or not train_summary.exists():
            continue

        try:
            with val_summary.open() as f:
                val_data = json.load(f)
            with train_summary.open() as f:
                train_data = json.load(f)

            val_pass_rate = val_data.get("assertion_pass_rate", 0.0)
            train_pass_rate = train_data.get("assertion_pass_rate", 0.0)
            val_tests_passed = sum(1 for t in val_data.get("tests", []) if t.get("passed", False))
            val_total_tests = val_data.get("total_tests", 0)
            train_tests_passed = sum(1 for t in train_data.get("tests", []) if t.get("passed", False))
            train_total_tests = train_data.get("total_tests", 0)

            gap = train_pass_rate - val_pass_rate

            results.append({
                "step": step,
                "train_pass_rate": train_pass_rate,
                "train_tests": f"{train_tests_passed}/{train_total_tests}",
                "val_pass_rate": val_pass_rate,
                "val_tests": f"{val_tests_passed}/{val_total_tests}",
                "gap": gap,
            })

            marker = ""
            print(f"Step {step}: Train={train_pass_rate:6.1%} ({train_tests_passed}/{train_total_tests} tests) | "
                  f"Val={val_pass_rate:6.1%} ({val_tests_passed}/{val_total_tests} tests) | "
                  f"Gap={gap:+6.1%}{marker}")

        except Exception as e:
            print(f"Step {step}: Error reading data: {e}")

    if not results:
        print("No results found")
        return

    # Find best validation checkpoint
    best_val = max(results, key=lambda x: x["val_pass_rate"])
    best_train = max(results, key=lambda x: x["train_pass_rate"])
    final = results[-1]

    print("\n" + "="*80)
    print("Model Selection Comparison:")
    print("-" * 80)

    print(f"\nBest Validation: Step {best_val['step']}")
    print(f"  Train: {best_val['train_pass_rate']:.1%} ({best_val['train_tests']} tests)")
    print(f"  Val:   {best_val['val_pass_rate']:.1%} ({best_val['val_tests']} tests)")
    print(f"  Gap:   {best_val['gap']:+.1%}")

    print(f"\nBest Training: Step {best_train['step']}")
    print(f"  Train: {best_train['train_pass_rate']:.1%} ({best_train['train_tests']} tests)")
    print(f"  Val:   {best_train['val_pass_rate']:.1%} ({best_train['val_tests']} tests)")
    print(f"  Gap:   {best_train['gap']:+.1%}")

    print(f"\nFinal (Current): Step {final['step']}")
    print(f"  Train: {final['train_pass_rate']:.1%} ({final['train_tests']} tests)")
    print(f"  Val:   {final['val_pass_rate']:.1%} ({final['val_tests']} tests)")
    print(f"  Gap:   {final['gap']:+.1%}")

    # Check test results
    test_dir = run_dir / "test"
    before_summary = test_dir / "before" / "run" / "evaluation_summary.json"
    after_summary = test_dir / "after" / "run" / "evaluation_summary.json"

    if before_summary.exists() and after_summary.exists():
        print("\n" + "="*80)
        print("Test Set Performance:")
        print("-" * 80)

        try:
            with before_summary.open() as f:
                before_data = json.load(f)
            with after_summary.open() as f:
                after_data = json.load(f)

            before_pass_rate = before_data.get("assertion_pass_rate", 0.0)
            after_pass_rate = after_data.get("assertion_pass_rate", 0.0)
            before_tests = sum(1 for t in before_data.get("tests", []) if t.get("passed", False))
            before_total = before_data.get("total_tests", 0)
            after_tests = sum(1 for t in after_data.get("tests", []) if t.get("passed", False))
            after_total = after_data.get("total_tests", 0)

            change = after_pass_rate - before_pass_rate

            print(f"\nBefore Training (Baseline):")
            print(f"  Pass Rate: {before_pass_rate:.1%} ({before_tests}/{before_total} tests)")

            print(f"\nAfter Training (Step {final['step']} - FINAL):")
            print(f"  Pass Rate: {after_pass_rate:.1%} ({after_tests}/{after_total} tests)")
            print(f"  Change:    {change:+.1%}")

            if change < 0:
                print(f"\n⚠️  TEST PERFORMANCE DEGRADED by {abs(change):.1%}")
                print(f"   This indicates overfitting to the training set.")
                print(f"\n💡 If we had selected Step {best_val['step']} (best validation),")
                print(f"   the gap would likely be smaller since validation gap was {best_val['gap']:+.1%}")
                print(f"   vs final gap of {final['gap']:+.1%}.")

        except Exception as e:
            print(f"Error reading test data: {e}")

    print("\n" + "="*80)
    print("Recommendations:")
    print("-" * 80)

    if best_val['step'] != final['step']:
        improvement = best_val['val_pass_rate'] - final['val_pass_rate']
        print(f"\n✓ Using 'validation' selection would have chosen Step {best_val['step']}")
        print(f"  instead of Step {final['step']}, improving validation by {improvement:+.1%}")
    else:
        print(f"\n✓ Step {final['step']} was already the best validation checkpoint")

    if abs(final['gap']) > 0.05:
        print(f"\n⚠️  Large train/val gap ({final['gap']:+.1%}) suggests overfitting")
        print(f"  Consider: early stopping, regularization, or more validation data")

    print()


if __name__ == "__main__":
    import sys

    _default_run_dir = Path(__file__).resolve().parent.parent / "runs" / "agent_builder_full"
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_run_dir
    analyze_run(run_dir)
