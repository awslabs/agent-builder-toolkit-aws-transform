#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Test script for evolution history module."""

from pathlib import Path
import tempfile
import json

from harness_evolver.evolution_history import (
    EvolutionHistory,
    EvaluationStats,
    StepDiff,
    get_code_diff_command,
)


def test_basic_workflow():
    """Test basic evolution history workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        snapshots_dir = tmpdir / "snapshots.git"
        snapshots_dir.mkdir()

        history = EvolutionHistory(
            path=tmpdir / "evolution_history.md",
            snapshots_dir=snapshots_dir,
        )

        # Simulate step 0
        step0_stats = EvaluationStats(
            pass_rate=0.4,
            n_pass=4,
            n_fail=6,
            n_total=10,
            passed_tasks=["task_a", "task_b", "task_c", "task_d"],
            failed_tasks=["task_e", "task_f", "task_g", "task_h", "task_i", "task_j"],
        )

        history.record_evaluation(
            step=0,
            train_stats=step0_stats,
            snapshot_sha="a1b2c3d4e5f6g7h8i9j0",
        )

        history.record_evolution(
            step=0,
            changes_summary="Initial evolution: added retry logic to handle timeouts",
            edits=["agent_loop.py", "config.yaml"],
        )

        # Simulate step 1 with improvements
        step1_stats = EvaluationStats(
            pass_rate=0.6,
            n_pass=6,
            n_fail=4,
            n_total=10,
            passed_tasks=["task_a", "task_b", "task_c", "task_d", "task_e", "task_f"],
            failed_tasks=["task_g", "task_h", "task_i", "task_j"],
        )

        diff = StepDiff.compute(step1_stats, step0_stats)

        history.record_evaluation(
            step=1,
            train_stats=step1_stats,
            diff=diff,
            snapshot_sha="b2c3d4e5f6g7h8i9j0k1",
        )

        history.record_evolution(
            step=1,
            changes_summary="Improved prompt clarity and added validation checks",
            rationale="Previous step showed timeout issues, added explicit validation",
            edits=["prompt.md", "validator.py"],
        )

        # Check file was created
        assert history.path.exists()
        content = history.path.read_text()

        # Check content has expected sections
        assert "# Harness Evolution History" in content
        assert "## Step 0" in content
        assert "## Step 1" in content
        assert "40.0% pass rate" in content
        assert "60.0% pass rate" in content
        assert "🎉 Flipped (fail→pass)" in content
        assert "task_e" in content
        assert "task_f" in content

        # Check snapshot references
        assert "Code snapshot" in content
        assert "a1b2c3d4e5f6" in content
        assert "b2c3d4e5f6g7" in content
        assert "git --git-dir=" in content

        # Test context retrieval
        context = history.get_context_for_prompt(max_steps=2)
        assert "## Step 0" in context
        assert "## Step 1" in context

        print("✅ Basic workflow test passed")
        print(f"\nGenerated history file ({len(content)} chars):")
        print("=" * 60)
        print(content)


def test_from_summary_json():
    """Test parsing evaluation_summary.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        summary_path = tmpdir / "evaluation_summary.json"

        # Create mock summary
        summary_data = {
            "assertion_pass_rate": 0.75,
            "total_tests": 8,
            "tests": [
                {"name": "test_1", "passed": True},
                {"name": "test_2", "passed": True},
                {"name": "test_3", "passed": False},
                {"name": "test_4", "passed": True},
                {"name": "test_5", "passed": True},
                {"name": "test_6", "passed": True},
                {"name": "test_7", "passed": False},
                {"name": "test_8", "passed": True},
            ],
        }

        summary_path.write_text(json.dumps(summary_data))

        stats = EvaluationStats.from_summary_json(summary_path)
        assert stats is not None
        assert stats.pass_rate == 0.75
        assert stats.n_pass == 6
        assert stats.n_fail == 2
        assert stats.n_total == 8
        assert "test_1" in stats.passed_tasks
        assert "test_3" in stats.failed_tasks

        print("✅ JSON parsing test passed")


def test_step_diff():
    """Test step diff computation."""
    prev_stats = EvaluationStats(
        pass_rate=0.5,
        n_pass=5,
        n_fail=5,
        n_total=10,
        passed_tasks=["a", "b", "c", "d", "e"],
        failed_tasks=["f", "g", "h", "i", "j"],
    )

    curr_stats = EvaluationStats(
        pass_rate=0.6,
        n_pass=6,
        n_fail=4,
        n_total=10,
        passed_tasks=["a", "b", "c", "d", "f", "g"],  # f, g flipped
        failed_tasks=["e", "h", "i", "j"],  # e regressed
    )

    diff = StepDiff.compute(curr_stats, prev_stats)
    assert diff is not None
    assert set(diff.flipped) == {"f", "g"}
    assert set(diff.regressed) == {"e"}
    assert set(diff.stable_pass) == {"a", "b", "c", "d"}
    assert set(diff.stable_fail) == {"h", "i", "j"}
    assert diff.net_change == 1  # 2 flipped - 1 regressed
    assert diff.retention_rate == 0.8  # 4 of 5 previously passing still passing

    print("✅ Step diff test passed")


def test_from_summary_json_uses_test_id():
    """Regression: real eval summaries key tasks by 'test_id', not 'name'.

    The original parser read t['name'] and the bare except swallowed the
    resulting KeyError -> returned None -> no metrics were ever recorded.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        summary_path = Path(tmpdir) / "evaluation_summary.json"
        summary_path.write_text(json.dumps({
            "assertion_pass_rate": 0.5,
            "total_tests": 2,
            "tests": [
                {"test_id": "generated_001", "passed": True},
                {"test_id": "generated_002", "passed": False},
            ],
        }))

        stats = EvaluationStats.from_summary_json(summary_path)
        assert stats is not None, "parser must not swallow the real schema"
        assert stats.passed_tasks == ["generated_001"]
        assert stats.failed_tasks == ["generated_002"]

        print("✅ test_id schema test passed")


def test_summarize_trace_summary_vs_rationale():
    """Regression: summary (clean final answer) and rationale (raw thinking)
    must be distinct, and the summary must not be truncated mid-sentence."""
    from harness_evolver.evolver.prompt import summarize_trace_for_traj

    with tempfile.TemporaryDirectory() as tmpdir:
        trace = Path(tmpdir) / "agent_trace.jsonl"
        long_result = "Final summary. " + ("x" * 5000)
        records = [
            {"type": "AssistantMessage", "content": [
                {"type": "TextBlock", "text": "Let me think about this..."},
                {"type": "ToolUseBlock", "name": "Edit",
                 "input": {"file_path": "/p/AGENT.md"}},
            ]},
            {"type": "ResultMessage", "result": long_result},
        ]
        trace.write_text("\n".join(json.dumps(r) for r in records))

        out = summarize_trace_for_traj(trace)
        # summary comes from ResultMessage.result, complete (no 2000-char cut)
        assert out["summary"] == long_result
        assert len(out["summary"]) > 2000
        # rationale is the raw thinking, distinct from the summary
        assert out["rationale"] == "Let me think about this..."
        assert out["summary"] != out["rationale"]
        assert out["edits"] == ["/p/AGENT.md"]

        print("✅ summary-vs-rationale test passed")


def test_code_diff_command():
    """Test git diff command generation."""
    snapshots_dir = Path("/tmp/my_run/snapshots.git")
    from_sha = "a1b2c3d4e5f6g7h8"
    to_sha = "x9y8z7w6v5u4t3s2"

    cmd = get_code_diff_command(snapshots_dir, from_sha, to_sha)

    assert "git --git-dir=" in cmd
    assert str(snapshots_dir) in cmd
    assert "diff" in cmd
    assert "a1b2c3d4e5f6" in cmd  # truncated to 12 chars
    assert "x9y8z7w6v5u4" in cmd  # truncated to 12 chars

    print("✅ Code diff command test passed")
    print(f"   Generated: {cmd}")


if __name__ == "__main__":
    test_basic_workflow()
    print()
    test_from_summary_json()
    print()
    test_from_summary_json_uses_test_id()
    print()
    test_summarize_trace_summary_vs_rationale()
    print()
    test_step_diff()
    print()
    test_code_diff_command()
    print("\n✅ All tests passed!")
