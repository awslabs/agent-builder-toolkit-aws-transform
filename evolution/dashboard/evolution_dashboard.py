#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Real-time dashboard for monitoring Agent Builder evolution.

This dashboard monitors the run directory and displays live metrics as the
evolution progresses. It provides:
- Live metrics table (train/val performance at each step)
- Interactive plots that auto-update
- Best checkpoint tracking
- Overfitting indicators

Usage:
    # Terminal 1: Start the evolution
    cd evolution
    source .venv/bin/activate
    PYTHONPATH=. python experiment/evolve_agent_builder.py

    # Terminal 2: Start the dashboard
    cd evolution
    source .venv/bin/activate
    python dashboard/evolution_dashboard.py --run-dir runs/agent_builder_full

    # Then open: http://localhost:5000
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import plotly.graph_objs as go
import plotly.utils
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# Global state
CURRENT_RUN_DIR = None
LAST_MODIFIED = {}


def collect_metrics(run_dir: Path):
    """Collect current metrics from the run directory."""
    train_dir = run_dir / "agent_builder_train"
    if not train_dir.exists():
        return None

    metrics = {
        "steps": [],
        "train_pass_rates": [],
        "train_test_rates": [],
        "train_assertions": [],
        "val_pass_rates": [],
        "val_test_rates": [],
        "val_assertions": [],
        "gaps": [],
        "timestamps": [],
    }

    # Collect from each completed step
    for step_dir in sorted(train_dir.glob("step_*")):
        step_match = re.search(r"step_(\d+)", step_dir.name)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Training results
        train_summary = step_dir / "agent_builder_train" / "run" / "evaluation_summary.json"
        if not train_summary.exists():
            continue

        try:
            with train_summary.open() as f:
                train_data = json.load(f)

            train_pass_rate = train_data.get("assertion_pass_rate", 0.0) * 100
            train_tests_passed = sum(1 for t in train_data.get("tests", []) if t.get("passed", False))
            train_total_tests = train_data.get("total_tests", 0)
            train_test_rate = train_tests_passed / train_total_tests * 100 if train_total_tests > 0 else 0
            train_assertions = f"{train_data.get('assertions_passed', 0)}/{train_data.get('total_assertions', 0)}"

            # Validation results
            val_summary = step_dir / "agent_builder_validation" / "run" / "evaluation_summary.json"
            if val_summary.exists():
                with val_summary.open() as f:
                    val_data = json.load(f)

                val_pass_rate = val_data.get("assertion_pass_rate", 0.0) * 100
                val_tests_passed = sum(1 for t in val_data.get("tests", []) if t.get("passed", False))
                val_total_tests = val_data.get("total_tests", 0)
                val_test_rate = val_tests_passed / val_total_tests * 100 if val_total_tests > 0 else 0
                val_assertions = f"{val_data.get('assertions_passed', 0)}/{val_data.get('total_assertions', 0)}"
                gap = train_pass_rate - val_pass_rate
            else:
                val_pass_rate = None
                val_test_rate = None
                val_assertions = "N/A"
                gap = None

            # Timestamp
            timestamp = datetime.fromtimestamp(train_summary.stat().st_mtime).strftime("%H:%M:%S")

            metrics["steps"].append(step)
            metrics["train_pass_rates"].append(train_pass_rate)
            metrics["train_test_rates"].append(train_test_rate)
            metrics["train_assertions"].append(train_assertions)
            metrics["val_pass_rates"].append(val_pass_rate)
            metrics["val_test_rates"].append(val_test_rate)
            metrics["val_assertions"].append(val_assertions)
            metrics["gaps"].append(gap)
            metrics["timestamps"].append(timestamp)

        except Exception as e:
            print(f"Error reading step {step}: {e}")
            continue

    # Check for test results
    test_before = run_dir / "test" / "before" / "run" / "evaluation_summary.json"
    test_after = run_dir / "test" / "after" / "run" / "evaluation_summary.json"

    metrics["test_before"] = None
    metrics["test_after"] = None

    if test_before.exists():
        try:
            with test_before.open() as f:
                data = json.load(f)
                metrics["test_before"] = {
                    "pass_rate": data.get("assertion_pass_rate", 0.0) * 100,
                    "tests_passed": sum(1 for t in data.get("tests", []) if t.get("passed", False)),
                    "total_tests": data.get("total_tests", 0),
                }
        except (OSError, json.JSONDecodeError) as e:
            # Non-fatal: the file may be mid-write or absent; leave test_before as None.
            print(f"Could not read test_before summary: {e}")

    if test_after.exists():
        try:
            with test_after.open() as f:
                data = json.load(f)
                metrics["test_after"] = {
                    "pass_rate": data.get("assertion_pass_rate", 0.0) * 100,
                    "tests_passed": sum(1 for t in data.get("tests", []) if t.get("passed", False)),
                    "total_tests": data.get("total_tests", 0),
                }
        except (OSError, json.JSONDecodeError) as e:
            # Non-fatal: the file may be mid-write or absent; leave test_after as None.
            print(f"Could not read test_after summary: {e}")

    # Find best validation checkpoint
    if metrics["val_pass_rates"] and any(v is not None for v in metrics["val_pass_rates"]):
        valid_indices = [i for i, v in enumerate(metrics["val_pass_rates"]) if v is not None]
        if valid_indices:
            best_val_idx = max(valid_indices, key=lambda i: metrics["val_pass_rates"][i])
            metrics["best_val_step"] = metrics["steps"][best_val_idx]
            metrics["best_val_rate"] = metrics["val_pass_rates"][best_val_idx]
        else:
            metrics["best_val_step"] = None
            metrics["best_val_rate"] = None
    else:
        metrics["best_val_step"] = None
        metrics["best_val_rate"] = None

    # Current status
    if metrics["steps"]:
        metrics["current_step"] = metrics["steps"][-1]
        metrics["latest_gap"] = metrics["gaps"][-1] if metrics["gaps"][-1] is not None else 0
    else:
        metrics["current_step"] = -1
        metrics["latest_gap"] = 0

    return metrics


def create_plots(metrics):
    """Create Plotly plots for the dashboard."""
    if not metrics or not metrics["steps"]:
        return None, None, None

    steps = metrics["steps"]

    # Plot 1: Assertion Pass Rates
    fig1 = go.Figure()

    fig1.add_trace(go.Scatter(
        x=steps, y=metrics["train_pass_rates"],
        mode='lines+markers',
        name='Training',
        line=dict(color='#2E86AB', width=3),
        marker=dict(size=10),
    ))

    fig1.add_trace(go.Scatter(
        x=steps, y=metrics["val_pass_rates"],
        mode='lines+markers',
        name='Validation',
        line=dict(color='#A23B72', width=3),
        marker=dict(size=10),
    ))

    # Add best validation marker
    if metrics["best_val_step"] is not None:
        fig1.add_trace(go.Scatter(
            x=[metrics["best_val_step"]],
            y=[metrics["best_val_rate"]],
            mode='markers',
            name=f'Best Val (Step {metrics["best_val_step"]})',
            marker=dict(size=20, color='#06A77D', symbol='star'),
        ))

    fig1.update_layout(
        title='Assertion Pass Rate Over Time',
        xaxis_title='Training Step',
        yaxis_title='Pass Rate (%)',
        hovermode='x unified',
        height=400,
        template='plotly_white',
        yaxis=dict(range=[70, 100]),
    )

    # Plot 2: Test Success Rates
    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(
        x=steps, y=metrics["train_test_rates"],
        mode='lines+markers',
        name='Training',
        line=dict(color='#2E86AB', width=3),
        marker=dict(size=10),
    ))

    fig2.add_trace(go.Scatter(
        x=steps, y=metrics["val_test_rates"],
        mode='lines+markers',
        name='Validation',
        line=dict(color='#A23B72', width=3),
        marker=dict(size=10),
    ))

    fig2.update_layout(
        title='Test Success Rate (All Assertions Pass)',
        xaxis_title='Training Step',
        yaxis_title='Success Rate (%)',
        hovermode='x unified',
        height=400,
        template='plotly_white',
        yaxis=dict(range=[0, 100]),
    )

    # Plot 3: Generalization Gap
    fig3 = go.Figure()

    colors = ['#06A77D' if (g is not None and g < 5) else '#F77F00' if (g is not None and g < 10) else '#D62828'
              for g in metrics["gaps"]]

    fig3.add_trace(go.Bar(
        x=steps,
        y=metrics["gaps"],
        name='Train - Val Gap',
        marker=dict(color=colors),
    ))

    # Add threshold lines
    fig3.add_hline(y=5, line_dash="dash", line_color="orange",
                   annotation_text="Warning (5%)", annotation_position="right")
    fig3.add_hline(y=10, line_dash="dash", line_color="red",
                   annotation_text="Danger (10%)", annotation_position="right")

    fig3.update_layout(
        title='Generalization Gap (Overfitting Indicator)',
        xaxis_title='Training Step',
        yaxis_title='Gap (%)',
        hovermode='x',
        height=400,
        template='plotly_white',
    )

    return (
        json.dumps(fig1, cls=plotly.utils.PlotlyJSONEncoder),
        json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder),
        json.dumps(fig3, cls=plotly.utils.PlotlyJSONEncoder),
    )


@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/metrics')
def get_metrics():
    """API endpoint to get current metrics."""
    if CURRENT_RUN_DIR is None:
        return jsonify({"error": "No run directory specified"}), 400

    metrics = collect_metrics(CURRENT_RUN_DIR)
    if metrics is None:
        return jsonify({"error": "No data available yet"}), 404

    plot1, plot2, plot3 = create_plots(metrics)

    return jsonify({
        "metrics": metrics,
        "plots": {
            "assertion_rates": plot1,
            "test_rates": plot2,
            "gaps": plot3,
        }
    })


@app.route('/api/status')
def get_status():
    """Get simple status for quick polling."""
    if CURRENT_RUN_DIR is None:
        return jsonify({"status": "no_run"})

    train_dir = CURRENT_RUN_DIR / "agent_builder_train"
    if not train_dir.exists():
        return jsonify({"status": "waiting", "message": "Waiting for training to start..."})

    # Check latest step
    step_dirs = sorted(train_dir.glob("step_*"))
    if not step_dirs:
        return jsonify({"status": "waiting", "message": "Waiting for first step..."})

    latest_step = step_dirs[-1]
    step_match = re.search(r"step_(\d+)", latest_step.name)
    step_num = int(step_match.group(1)) if step_match else 0

    # Check if step is complete
    train_summary = latest_step / "agent_builder_train" / "run" / "evaluation_summary.json"
    val_summary = latest_step / "agent_builder_validation" / "run" / "evaluation_summary.json"

    if not train_summary.exists():
        return jsonify({
            "status": "running",
            "step": step_num,
            "stage": "training",
            "message": f"Running training for step {step_num}..."
        })
    elif not val_summary.exists():
        return jsonify({
            "status": "running",
            "step": step_num,
            "stage": "validation",
            "message": f"Running validation for step {step_num}..."
        })
    else:
        # Check for final eval
        final_dir = train_dir / "final_eval"
        if final_dir.exists():
            return jsonify({
                "status": "complete",
                "message": "Evolution complete!"
            })
        else:
            return jsonify({
                "status": "running",
                "step": step_num,
                "stage": "editing",
                "message": f"Step {step_num} complete, evolver running..."
            })


def main():
    parser = argparse.ArgumentParser(description="Real-time evolution dashboard")
    parser.add_argument("--run-dir", type=str, required=True,
                       help="Path to the run directory to monitor")
    parser.add_argument("--port", type=int, default=5000,
                       help="Port to run the dashboard on (default: 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                       help="Host to bind to (default: 127.0.0.1)")
    args = parser.parse_args()

    global CURRENT_RUN_DIR
    CURRENT_RUN_DIR = Path(args.run_dir).resolve()

    if not CURRENT_RUN_DIR.exists():
        print(f"Creating run directory: {CURRENT_RUN_DIR}")
        CURRENT_RUN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*80}")
    print("Agent Builder Evolution Dashboard")
    print(f"{'='*80}")
    print(f"\nMonitoring: {CURRENT_RUN_DIR}")
    print(f"\nDashboard URL: http://{args.host}:{args.port}")
    print("\nPress Ctrl+C to stop\n")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
