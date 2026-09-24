# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for TestCase dataclass and TestCaseLoader."""

import json
import tempfile
from pathlib import Path

import pytest


class TestTestCase:
    def test_create_minimal(self):
        from eval_runner.test_case import TestCase

        tc = TestCase(id="t1", name="basic test", user_message="hello")
        assert tc.id == "t1"
        assert tc.name == "basic test"
        assert tc.user_message == "hello"
        assert tc.description == ""
        assert tc.complexity == "medium"
        assert tc.tags == []
        assert tc.max_turns == 1
        assert tc.timeout_seconds == 300
        assert tc.simulated_human_guidance is None
        assert tc.metadata == {}
        assert tc.assertions == []

    def test_create_full(self):
        from eval_runner.test_case import TestCase

        tc = TestCase(
            id="onboarding-intermediate",
            name="Intermediate onboarding",
            user_message="I just installed the power",
            description="Tests the onboarding flow",
            complexity="medium",
            tags=["onboarding", "intermediate"],
            max_turns=12,
            timeout_seconds=600,
            simulated_human_guidance="You are a developer...",
            metadata={"domain": "agent_builder"},
            assertions=[
                {"name": "check1", "type": "llm_judge", "check": "Did X happen?"}
            ],
        )
        assert tc.max_turns == 12
        assert tc.tags == ["onboarding", "intermediate"]
        assert len(tc.assertions) == 1

    def test_prompt_fallback(self):
        """If user_message is not provided but prompt is, use prompt as fallback."""
        from eval_runner.test_case import TestCase

        tc = TestCase.from_dict({"id": "t1", "name": "test", "prompt": "fallback msg"})
        assert tc.user_message == "fallback msg"

    def test_user_message_preferred_over_prompt(self):
        """user_message takes precedence when both are present."""
        from eval_runner.test_case import TestCase

        tc = TestCase.from_dict({
            "id": "t1",
            "name": "test",
            "user_message": "primary",
            "prompt": "fallback",
        })
        assert tc.user_message == "primary"

    def test_from_dict_missing_required_raises(self):
        from eval_runner.test_case import TestCase

        with pytest.raises((KeyError, ValueError)):
            TestCase.from_dict({"name": "no id or message"})

    def test_to_scenario_carries_complexity(self):
        from eval_runner.test_case import TestCase

        tc = TestCase(
            id="t1", name="t", user_message="m", complexity="hard", tags=["x", "y"]
        )
        scenario = tc.to_scenario()
        assert scenario.complexity == "hard"
        assert scenario.tags == ["x", "y"]

    def test_eval_case_complexity_default_medium(self):
        from eval_runner.execution.runner import EvalCase

        case = EvalCase(
            id="c1", name="c", prompt="p", description="d", assertions=[]
        )
        assert case.complexity == "medium"


class TestTestCaseLoader:
    def _write_test_file(self, path: Path, data: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_load_from_file(self):
        from eval_runner.test_case import TestCaseLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tests.json"
            self._write_test_file(path, [
                {"id": "t1", "name": "test 1", "user_message": "hello"},
                {"id": "t2", "name": "test 2", "user_message": "world"},
            ])
            cases = TestCaseLoader.from_file(path)
            assert len(cases) == 2
            assert cases[0].id == "t1"
            assert cases[1].user_message == "world"

    def test_load_from_directory(self):
        from eval_runner.test_case import TestCaseLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_test_file(
                Path(tmpdir) / "a.json",
                [{"id": "a1", "name": "a", "user_message": "msg_a"}],
            )
            self._write_test_file(
                Path(tmpdir) / "b.json",
                [{"id": "b1", "name": "b", "user_message": "msg_b"}],
            )
            cases = TestCaseLoader.from_directory(Path(tmpdir))
            assert len(cases) == 2
            ids = {tc.id for tc in cases}
            assert ids == {"a1", "b1"}

    def test_load_from_directory_ignores_non_json(self):
        from eval_runner.test_case import TestCaseLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_test_file(
                Path(tmpdir) / "valid.json",
                [{"id": "v1", "name": "v", "user_message": "msg"}],
            )
            (Path(tmpdir) / "readme.md").write_text("# not a test")
            cases = TestCaseLoader.from_directory(Path(tmpdir))
            assert len(cases) == 1

    def test_filter_by_complexity(self):
        from eval_runner.test_case import TestCase, TestCaseLoader

        cases = [
            TestCase(id="e1", name="easy", user_message="m", complexity="easy"),
            TestCase(id="m1", name="med", user_message="m", complexity="medium"),
            TestCase(id="h1", name="hard", user_message="m", complexity="hard"),
        ]
        filtered = TestCaseLoader.filter_by_complexity(cases, "easy")
        assert len(filtered) == 1
        assert filtered[0].id == "e1"

    def test_filter_by_tag(self):
        from eval_runner.test_case import TestCase, TestCaseLoader

        cases = [
            TestCase(id="t1", name="a", user_message="m", tags=["onboarding", "fast"]),
            TestCase(id="t2", name="b", user_message="m", tags=["migration"]),
            TestCase(id="t3", name="c", user_message="m", tags=["onboarding"]),
        ]
        filtered = TestCaseLoader.filter_by_tag(cases, "onboarding")
        assert len(filtered) == 2
        assert {tc.id for tc in filtered} == {"t1", "t3"}

    def test_load_real_test_sample(self):
        """Load the actual onboarding_intermediate.json from the repo."""
        from eval_runner.test_case import TestCaseLoader

        # tests/eval_runner/ -> tests/ -> evaluation/
        sample_path = (
            Path(__file__).resolve().parent.parent.parent
            / "test_samples"
            / "onboarding_intermediate.json"
        )
        if not sample_path.exists():
            pytest.skip("test_samples not available")
        cases = TestCaseLoader.from_file(sample_path)
        assert len(cases) == 1
        tc = cases[0]
        assert tc.id == "onboarding-intermediate"
        assert tc.max_turns == 12
        assert len(tc.assertions) == 12
        assert tc.simulated_human_guidance is not None
