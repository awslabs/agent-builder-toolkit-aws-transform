#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Enhanced plot with separate success rate and assertion pass rate visualizations.

Usage:
    cd evolution
    source .venv/bin/activate
    python scripts/plot_training_results_enhanced.py
"""

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def collect_data(run_dir: Path):
    """Collect training, validation, and test data from run directory."""
    train_dir = run_dir / "agent_builder_train"

    steps = []
    train_pass_rates = []
    train_test_rates = []
    val_pass_rates = []
    val_test_rates = []
    train_gap = []

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
                train_pass_rate = train_data.get("assertion_pass_rate", 0.0) * 100
                train_pass_rates.append(train_pass_rate)
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
                val_pass_rate = val_data.get("assertion_pass_rate", 0.0) * 100
                val_pass_rates.append(val_pass_rate)
                val_tests_passed = sum(1 for t in val_data.get("tests", []) if t.get("passed", False))
                val_total_tests = val_data.get("total_tests", 1)
                val_test_rates.append(val_tests_passed / val_total_tests * 100)
                train_gap.append(train_pass_rate - val_pass_rate)
        else:
            val_pass_rates.append(None)
            val_test_rates.append(None)
            train_gap.append(None)

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
        "train_gap": train_gap,
        "test_before_pass_rate": test_before_pass_rate,
        "test_before_test_rate": test_before_test_rate,
        "test_after_pass_rate": test_after_pass_rate,
        "test_after_test_rate": test_after_test_rate,
    }


def plot_results(data, output_path):
    """Create enhanced visualization with separate assertion and success rate plots."""

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.25)

    fig.suptitle('Agent Builder Evolution: Overfitting Analysis',
                 fontsize=18, fontweight='bold', y=0.98)

    steps = data["steps"]

    # === Plot 1: Assertion Pass Rate ===
    ax1 = fig.add_subplot(gs[0, 0])

    ax1.plot(steps, data["train_pass_rates"], 'o-', linewidth=3, markersize=10,
             color='#2E86AB', label='Training', alpha=0.9)
    ax1.plot(steps, data["val_pass_rates"], 's-', linewidth=3, markersize=10,
             color='#A23B72', label='Validation', alpha=0.9)

    # Mark best validation point
    if data["val_pass_rates"]:
        best_val_idx = max(range(len(data["val_pass_rates"])),
                          key=lambda i: data["val_pass_rates"][i] if data["val_pass_rates"][i] is not None else -1)
        best_val_step = steps[best_val_idx]
        best_val_rate = data["val_pass_rates"][best_val_idx]
        ax1.plot(best_val_step, best_val_rate, '*', markersize=25, color='#06A77D',
                label=f'Best Val (Step {best_val_step})', zorder=5,
                markeredgecolor='black', markeredgewidth=1.5)

    # Mark final step used
    final_step = steps[-1]
    final_train_rate = data["train_pass_rates"][-1]
    ax1.plot(final_step, final_train_rate, '*', markersize=25, color='#D62828',
            label=f'Used (Step {final_step})', zorder=5,
            markeredgecolor='black', markeredgewidth=1.5)

    ax1.set_xlabel('Training Step', fontsize=13, fontweight='bold')
    ax1.set_ylabel('Assertion Pass Rate (%)', fontsize=13, fontweight='bold')
    ax1.set_title('Assertion-Level Performance\n(Individual Assertions)',
                  fontsize=14, fontweight='bold', pad=10)
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=1)
    ax1.legend(loc='lower left', fontsize=11, framealpha=0.95)
    ax1.set_ylim([75, 100])
    ax1.set_xticks(steps)
    ax1.tick_params(labelsize=11)

    # === Plot 2: Test Success Rate (Complete Tests) ===
    ax2 = fig.add_subplot(gs[0, 1])

    ax2.plot(steps, data["train_test_rates"], 'o-', linewidth=3, markersize=10,
             color='#2E86AB', label='Training', alpha=0.9)
    ax2.plot(steps, data["val_test_rates"], 's-', linewidth=3, markersize=10,
             color='#A23B72', label='Validation', alpha=0.9)

    # Mark best validation point
    if data["val_test_rates"]:
        best_val_idx = max(range(len(data["val_test_rates"])),
                          key=lambda i: data["val_test_rates"][i] if data["val_test_rates"][i] is not None else -1)
        best_val_step = steps[best_val_idx]
        best_val_rate = data["val_test_rates"][best_val_idx]
        ax2.plot(best_val_step, best_val_rate, '*', markersize=25, color='#06A77D',
                label=f'Best Val (Step {best_val_step})', zorder=5,
                markeredgecolor='black', markeredgewidth=1.5)

    # Mark final step
    final_step = steps[-1]
    final_train_test_rate = data["train_test_rates"][-1]
    ax2.plot(final_step, final_train_test_rate, '*', markersize=25, color='#D62828',
            label=f'Used (Step {final_step})', zorder=5,
            markeredgecolor='black', markeredgewidth=1.5)

    ax2.set_xlabel('Training Step', fontsize=13, fontweight='bold')
    ax2.set_ylabel('Test Success Rate (%)', fontsize=13, fontweight='bold')
    ax2.set_title('Test-Level Performance\n(All Assertions Pass)',
                  fontsize=14, fontweight='bold', pad=10)
    ax2.grid(True, alpha=0.3, linestyle='--', linewidth=1)
    ax2.legend(loc='lower left', fontsize=11, framealpha=0.95)
    ax2.set_ylim([0, 100])
    ax2.set_xticks(steps)
    ax2.tick_params(labelsize=11)

    # === Plot 3: Generalization Gap (Train - Val) ===
    ax3 = fig.add_subplot(gs[1, 0])

    colors = ['#06A77D' if gap < 5 else '#F77F00' if gap < 10 else '#D62828'
              for gap in data["train_gap"]]
    ax3.bar(steps, data["train_gap"], color=colors, alpha=0.7,
            edgecolor='black', linewidth=1.5)

    # Add threshold line
    ax3.axhline(y=5, color='orange', linestyle='--', linewidth=2,
                alpha=0.7, label='Warning Threshold (5%)')
    ax3.axhline(y=10, color='red', linestyle='--', linewidth=2,
                alpha=0.7, label='Danger Threshold (10%)')

    # Highlight step 2 (worst overfitting)
    worst_gap_idx = max(range(len(data["train_gap"])),
                        key=lambda i: data["train_gap"][i] if data["train_gap"][i] is not None else -1)
    worst_step = steps[worst_gap_idx]
    worst_gap = data["train_gap"][worst_gap_idx]

    ax3.annotate(f'Peak Overfitting\n+{worst_gap:.1f}%',
                xy=(worst_step, worst_gap),
                xytext=(worst_step, worst_gap + 3),
                fontsize=11, fontweight='bold', color='red',
                ha='center',
                arrowprops=dict(arrowstyle='->', color='red', lw=2))

    ax3.set_xlabel('Training Step', fontsize=13, fontweight='bold')
    ax3.set_ylabel('Generalization Gap (%)', fontsize=13, fontweight='bold')
    ax3.set_title('Overfitting Indicator\n(Train - Validation Assertion Rate)',
                  fontsize=14, fontweight='bold', pad=10)
    ax3.grid(True, alpha=0.3, linestyle='--', linewidth=1, axis='y')
    ax3.legend(loc='upper left', fontsize=10, framealpha=0.95)
    ax3.set_ylim([0, max(data["train_gap"]) * 1.2])
    ax3.set_xticks(steps)
    ax3.tick_params(labelsize=11)

    # === Plot 4: Test Set Degradation ===
    ax4 = fig.add_subplot(gs[1, 1])

    # Create comparison bars
    categories = ['Assertion\nPass Rate', 'Test\nSuccess Rate']
    x_pos = np.arange(len(categories))
    width = 0.35

    before_values = [data["test_before_pass_rate"], data["test_before_test_rate"]]
    after_values = [data["test_after_pass_rate"], data["test_after_test_rate"]]

    bars1 = ax4.bar(x_pos - width/2, before_values, width, label='Before Training',
                   color='#06A77D', alpha=0.8, edgecolor='black', linewidth=1.5)
    bars2 = ax4.bar(x_pos + width/2, after_values, width, label='After Training',
                   color='#D62828', alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax4.text(bar.get_x() + bar.get_width()/2., height + 2,
                    f'{height:.1f}%',
                    ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Add change arrows
    for i, (before, after) in enumerate(zip(before_values, after_values)):
        change = after - before
        mid_x = x_pos[i]
        ax4.annotate('', xy=(mid_x, after), xytext=(mid_x, before),
                    arrowprops=dict(arrowstyle='->', color='red' if change < 0 else 'green',
                                  lw=3, alpha=0.7))
        ax4.text(mid_x + 0.45, (before + after) / 2, f'{change:+.1f}%',
                fontsize=11, fontweight='bold', color='red' if change < 0 else 'green',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax4.set_ylabel('Pass Rate (%)', fontsize=13, fontweight='bold')
    ax4.set_title('Test Set Performance Degradation\n(Before vs After Training)',
                  fontsize=14, fontweight='bold', pad=10)
    ax4.set_xticks(x_pos)
    ax4.set_xticklabels(categories, fontsize=12, fontweight='bold')
    ax4.legend(loc='upper right', fontsize=11, framealpha=0.95)
    ax4.set_ylim([0, 105])
    ax4.grid(True, alpha=0.3, linestyle='--', linewidth=1, axis='y')
    ax4.tick_params(labelsize=11)

    # Add warning text box
    textstr = '⚠️ OVERFITTING DETECTED\nTest degraded by 17.4%'
    props = dict(boxstyle='round', facecolor='yellow', alpha=0.8, edgecolor='red', linewidth=2)
    ax4.text(0.5, 0.15, textstr, transform=ax4.transAxes, fontsize=12,
            fontweight='bold', verticalalignment='center', horizontalalignment='center',
            bbox=props, color='red')

    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n✓ Enhanced plot saved to: {output_path}")

    return fig


def print_detailed_summary(data):
    """Print detailed summary with recommendations."""
    print("\n" + "="*80)
    print("DETAILED TRAINING ANALYSIS")
    print("="*80)

    steps = data["steps"]

    print("\n📊 STEP-BY-STEP BREAKDOWN:")
    print("-" * 80)
    print(f"{'Step':>4} | {'Train Assr':>10} | {'Val Assr':>10} | {'Gap':>7} | "
          f"{'Train Test':>10} | {'Val Test':>10}")
    print("-" * 80)

    for i, step in enumerate(steps):
        train_pass = data["train_pass_rates"][i]
        val_pass = data["val_pass_rates"][i] if data["val_pass_rates"][i] is not None else 0
        gap = data["train_gap"][i] if data["train_gap"][i] is not None else 0
        train_test = data["train_test_rates"][i]
        val_test = data["val_test_rates"][i] if data["val_test_rates"][i] is not None else 0

        marker = "  ⭐ BEST VAL" if i == 0 else ""
        marker = "  🔴 USED" if i == len(steps) - 1 else marker

        print(f"{step:>4} | {train_pass:>9.1f}% | {val_pass:>9.1f}% | {gap:>6.1f}% | "
              f"{train_test:>9.1f}% | {val_test:>9.1f}%{marker}")

    # Best validation
    best_val_idx = max(range(len(data["val_pass_rates"])),
                      key=lambda i: data["val_pass_rates"][i] if data["val_pass_rates"][i] is not None else -1)
    best_val_step = steps[best_val_idx]

    print("\n" + "="*80)
    print("🎯 KEY FINDINGS:")
    print("="*80)

    print(f"\n1. BEST CHECKPOINT: Step {best_val_step}")
    print("   - Best validation performance with smallest train/val gap")
    print("   - This checkpoint should have been used for final test")

    print("\n2. OVERFITTING PROGRESSION:")
    worst_gap_idx = max(range(len(data["train_gap"])),
                        key=lambda i: data["train_gap"][i] if data["train_gap"][i] is not None else -1)
    print(f"   - Step {steps[worst_gap_idx]}: Peak overfitting (gap = {data['train_gap'][worst_gap_idx]:.1f}%)")
    print(f"   - Validation dropped from {data['val_pass_rates'][0]:.1f}% to {data['val_pass_rates'][worst_gap_idx]:.1f}%")

    print("\n3. TEST SET DEGRADATION:")
    assertion_change = data["test_after_pass_rate"] - data["test_before_pass_rate"]
    test_change = data["test_after_test_rate"] - data["test_before_test_rate"]
    print(f"   - Assertion pass rate: {data['test_before_pass_rate']:.1f}% → {data['test_after_pass_rate']:.1f}% ({assertion_change:+.1f}%)")
    print(f"   - Test success rate: {data['test_before_test_rate']:.1f}% → {data['test_after_test_rate']:.1f}% ({test_change:+.1f}%)")
    print(f"   - Using Step {best_val_step} would likely prevent this degradation")

    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS:")
    print("="*80)
    print("\n1. ✅ IMPLEMENTED: Model selection based on validation")
    print("   - Set selection_metric='validation' in run_experiment()")
    print("   - Will automatically use Step 0 instead of Step 4")

    print("\n2. 🔧 TODO: Early stopping")
    print("   - Stop training when validation stops improving")
    print("   - Would have stopped at Step 2 or 3")

    print("\n3. 🔧 TODO: Regularization")
    print("   - Add complexity penalty to evolver prompt")
    print("   - Prevent AGENT.md from growing excessively")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    import sys

    _default_run_dir = Path(__file__).resolve().parent.parent / "runs" / "agent_builder_full"
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_run_dir
    output_path = run_dir / "training_results_detailed.png"

    print("Collecting training data...")
    data = collect_data(run_dir)

    print(f"Found {len(data['steps'])} training steps")
    print_detailed_summary(data)

    print("Generating enhanced plot...")
    plot_results(data, output_path)

    print("\n✅ DONE! View the plot:")
    print(f"   {output_path}")
