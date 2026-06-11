#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Plot training, validation, and test results from evolution run.

Usage:
    cd evolution
    source .venv/bin/activate
    python scripts/plot_training_results.py
"""

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


def collect_data(run_dir: Path):
    """Collect training, validation, and test data from run directory."""
    train_dir = run_dir / "agent_builder_train"

    steps = []
    train_pass_rates = []
    train_test_rates = []
    val_pass_rates = []
    val_test_rates = []

    # Collect data from each step
    for step_dir in sorted(train_dir.glob("step_*")):
        step_match = re.search(r"step_(\d+)", step_dir.name)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Training results
        train_summary = step_dir / "agent_builder_train" / "run" / "evaluation_summary.json"
        if train_summary.exists():
            with train_summary.open() as f:
                train_data = json.load(f)
                train_pass_rates.append(train_data.get("assertion_pass_rate", 0.0) * 100)
                train_tests_passed = sum(1 for t in train_data.get("tests", []) if t.get("passed", False))
                train_total_tests = train_data.get("total_tests", 1)
                train_test_rates.append(train_tests_passed / train_total_tests * 100)
        else:
            continue

        # Validation results
        val_summary = step_dir / "agent_builder_validation" / "run" / "evaluation_summary.json"
        if val_summary.exists():
            with val_summary.open() as f:
                val_data = json.load(f)
                val_pass_rates.append(val_data.get("assertion_pass_rate", 0.0) * 100)
                val_tests_passed = sum(1 for t in val_data.get("tests", []) if t.get("passed", False))
                val_total_tests = val_data.get("total_tests", 1)
                val_test_rates.append(val_tests_passed / val_total_tests * 100)
        else:
            val_pass_rates.append(None)
            val_test_rates.append(None)

        steps.append(step)

    # Test results (before and after only)
    test_before = run_dir / "test" / "before" / "run" / "evaluation_summary.json"
    test_after = run_dir / "test" / "after" / "run" / "evaluation_summary.json"

    test_before_pass_rate = None
    test_before_test_rate = None
    test_after_pass_rate = None
    test_after_test_rate = None

    if test_before.exists():
        with test_before.open() as f:
            data = json.load(f)
            test_before_pass_rate = data.get("assertion_pass_rate", 0.0) * 100
            tests_passed = sum(1 for t in data.get("tests", []) if t.get("passed", False))
            total_tests = data.get("total_tests", 1)
            test_before_test_rate = tests_passed / total_tests * 100

    if test_after.exists():
        with test_after.open() as f:
            data = json.load(f)
            test_after_pass_rate = data.get("assertion_pass_rate", 0.0) * 100
            tests_passed = sum(1 for t in data.get("tests", []) if t.get("passed", False))
            total_tests = data.get("total_tests", 1)
            test_after_test_rate = tests_passed / total_tests * 100

    return {
        "steps": steps,
        "train_pass_rates": train_pass_rates,
        "train_test_rates": train_test_rates,
        "val_pass_rates": val_pass_rates,
        "val_test_rates": val_test_rates,
        "test_before_pass_rate": test_before_pass_rate,
        "test_before_test_rate": test_before_test_rate,
        "test_after_pass_rate": test_after_pass_rate,
        "test_after_test_rate": test_after_test_rate,
    }


def plot_results(data, output_path):
    """Create visualization of training results."""

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    fig.suptitle('Agent Builder Evolution: Training Progress and Overfitting',
                 fontsize=16, fontweight='bold', y=0.995)

    steps = data["steps"]

    # === Plot 1: Assertion Pass Rates ===
    ax1.plot(steps, data["train_pass_rates"], 'o-', linewidth=2, markersize=8,
             color='#2E86AB', label='Training', alpha=0.9)
    ax1.plot(steps, data["val_pass_rates"], 's-', linewidth=2, markersize=8,
             color='#A23B72', label='Validation', alpha=0.9)

    # Add test before/after as horizontal lines
    if data["test_before_pass_rate"] is not None:
        ax1.axhline(y=data["test_before_pass_rate"], color='#06A77D',
                   linestyle='--', linewidth=2, alpha=0.7, label='Test (Before)')

    if data["test_after_pass_rate"] is not None:
        ax1.axhline(y=data["test_after_pass_rate"], color='#D62828',
                   linestyle='--', linewidth=2, alpha=0.7, label='Test (After)')

    # Mark best validation point
    if data["val_pass_rates"]:
        best_val_idx = max(range(len(data["val_pass_rates"])),
                          key=lambda i: data["val_pass_rates"][i] if data["val_pass_rates"][i] is not None else -1)
        best_val_step = steps[best_val_idx]
        best_val_rate = data["val_pass_rates"][best_val_idx]
        ax1.plot(best_val_step, best_val_rate, 'g*', markersize=20,
                label=f'Best Val (Step {best_val_step})', zorder=5)

    # Mark final step used for test
    final_step = steps[-1]
    final_train_rate = data["train_pass_rates"][-1]
    ax1.plot(final_step, final_train_rate, 'r*', markersize=20,
            label=f'Used for Test (Step {final_step})', zorder=5)

    ax1.set_xlabel('Training Step', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Assertion Pass Rate (%)', fontsize=12, fontweight='bold')
    ax1.set_title('Assertion-Level Performance', fontsize=14, fontweight='bold', pad=10)
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.legend(loc='best', fontsize=10, framealpha=0.9)
    ax1.set_ylim([65, 100])
    ax1.set_xticks(steps)

    # Add annotation for overfitting
    if data["test_before_pass_rate"] and data["test_after_pass_rate"]:
        change = data["test_after_pass_rate"] - data["test_before_pass_rate"]
        mid_y = (data["test_before_pass_rate"] + data["test_after_pass_rate"]) / 2
        ax1.annotate(f'Test Degradation:\n{change:.1f}%',
                    xy=(steps[-1] + 0.3, mid_y),
                    fontsize=10, color='red', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))

    # === Plot 2: Test Pass Rates (Complete Tests) ===
    ax2.plot(steps, data["train_test_rates"], 'o-', linewidth=2, markersize=8,
             color='#2E86AB', label='Training', alpha=0.9)
    ax2.plot(steps, data["val_test_rates"], 's-', linewidth=2, markersize=8,
             color='#A23B72', label='Validation', alpha=0.9)

    # Add test before/after
    if data["test_before_test_rate"] is not None:
        ax2.axhline(y=data["test_before_test_rate"], color='#06A77D',
                   linestyle='--', linewidth=2, alpha=0.7, label='Test (Before)')

    if data["test_after_test_rate"] is not None:
        ax2.axhline(y=data["test_after_test_rate"], color='#D62828',
                   linestyle='--', linewidth=2, alpha=0.7, label='Test (After)')

    # Mark best validation point
    if data["val_test_rates"]:
        best_val_idx = max(range(len(data["val_test_rates"])),
                          key=lambda i: data["val_test_rates"][i] if data["val_test_rates"][i] is not None else -1)
        best_val_step = steps[best_val_idx]
        best_val_rate = data["val_test_rates"][best_val_idx]
        ax2.plot(best_val_step, best_val_rate, 'g*', markersize=20,
                label=f'Best Val (Step {best_val_step})', zorder=5)

    # Mark final step
    final_step = steps[-1]
    final_train_test_rate = data["train_test_rates"][-1]
    ax2.plot(final_step, final_train_test_rate, 'r*', markersize=20,
            label=f'Used for Test (Step {final_step})', zorder=5)

    ax2.set_xlabel('Training Step', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Complete Test Pass Rate (%)', fontsize=12, fontweight='bold')
    ax2.set_title('Test-Level Performance (All Assertions Pass)', fontsize=14, fontweight='bold', pad=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='best', fontsize=10, framealpha=0.9)
    ax2.set_ylim([0, 100])
    ax2.set_xticks(steps)

    # Add annotation for test performance
    if data["test_before_test_rate"] and data["test_after_test_rate"]:
        change = data["test_after_test_rate"] - data["test_before_test_rate"]
        mid_y = (data["test_before_test_rate"] + data["test_after_test_rate"]) / 2
        ax2.annotate(f'Test Degradation:\n{change:.1f}%',
                    xy=(steps[-1] + 0.3, mid_y),
                    fontsize=10, color='red', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n✓ Plot saved to: {output_path}")

    return fig


def print_summary(data):
    """Print summary statistics."""
    print("\n" + "="*80)
    print("Training Summary")
    print("="*80)

    steps = data["steps"]

    # Find best validation
    if data["val_pass_rates"]:
        best_val_idx = max(range(len(data["val_pass_rates"])),
                          key=lambda i: data["val_pass_rates"][i] if data["val_pass_rates"][i] is not None else -1)
        best_val_step = steps[best_val_idx]
        best_val_rate = data["val_pass_rates"][best_val_idx]
        best_train_at_val = data["train_pass_rates"][best_val_idx]
        gap_at_best = best_train_at_val - best_val_rate

        print(f"\nBest Validation: Step {best_val_step}")
        print(f"  Validation:     {best_val_rate:.1f}%")
        print(f"  Training:       {best_train_at_val:.1f}%")
        print(f"  Train/Val Gap:  {gap_at_best:+.1f}%")

    # Final step stats
    final_idx = -1
    final_step = steps[final_idx]
    final_train = data["train_pass_rates"][final_idx]
    final_val = data["val_pass_rates"][final_idx] if data["val_pass_rates"][final_idx] is not None else 0
    final_gap = final_train - final_val

    print(f"\nFinal Step (Used): Step {final_step}")
    print(f"  Validation:     {final_val:.1f}%")
    print(f"  Training:       {final_train:.1f}%")
    print(f"  Train/Val Gap:  {final_gap:+.1f}%")

    # Test results
    if data["test_before_pass_rate"] and data["test_after_pass_rate"]:
        change = data["test_after_pass_rate"] - data["test_before_pass_rate"]
        print("\nTest Set Performance:")
        print(f"  Before Training:  {data['test_before_pass_rate']:.1f}%")
        print(f"  After Training:   {data['test_after_pass_rate']:.1f}%")
        print(f"  Change:           {change:+.1f}% {'⚠️ DEGRADED' if change < 0 else '✓ IMPROVED'}")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    import sys

    _default_run_dir = Path(__file__).resolve().parent.parent / "runs" / "agent_builder_full"
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_run_dir
    output_path = run_dir / "training_results.png"

    print("Collecting data from run...")
    data = collect_data(run_dir)

    print(f"Found {len(data['steps'])} training steps")
    print_summary(data)

    print("Generating plot...")
    plot_results(data, output_path)

    print("\n✓ Done! Open the plot with:")
    print(f"  xdg-open {output_path}")
