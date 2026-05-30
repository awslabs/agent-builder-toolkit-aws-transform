# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration test: the framework ingests this repo's curated test samples.

These tests exercise the wiring described in ``evaluation/run_eval.py`` — the
framework loads the scenarios in ``evaluation/test_samples/`` end-to-end
(JSON → EvalCase → assertions) and an ``EvalConfig`` can be constructed against
the ``evaluation/agent_under_test/`` agent definition.

They are pure ingestion/validation checks: no ``agent-cli`` subprocess and no
live model calls, so they run in CI without external dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval_runner.config import ExecutionConfig as EvalConfig
from eval_runner.execution.loader import list_scenarios, load_scenarios

# eval_runner/tests/ -> eval_runner/ -> evaluation/
EVAL_DIR = Path(__file__).resolve().parent.parent.parent
TEST_SAMPLES = EVAL_DIR / "test_samples"
AGENT_UNDER_TEST = EVAL_DIR / "agent_under_test"

try:
    import jsonschema  # noqa: F401

    _HAS_JSONSCHEMA = True
except (ImportError, ModuleNotFoundError):
    _HAS_JSONSCHEMA = False

needs_jsonschema = pytest.mark.skipif(
    not _HAS_JSONSCHEMA, reason="jsonschema (rpds native ext) not available on this platform"
)


class TestTestSamplesLoad:
    """The curated test samples load through the framework loader."""

    def test_samples_dir_exists(self) -> None:
        assert TEST_SAMPLES.is_dir(), f"Missing test samples dir: {TEST_SAMPLES}"

    @needs_jsonschema
    def test_loads_and_validates_against_schema(self) -> None:
        """Every sample loads AND passes schema validation (default validate=True)."""
        scenarios = load_scenarios(TEST_SAMPLES)
        assert scenarios, "No scenarios loaded from test_samples/"

    def test_onboarding_sample_parsed(self) -> None:
        """The onboarding sample parses into a fully-populated EvalCase."""
        scenarios = load_scenarios(
            TEST_SAMPLES, validate=False, filter_ids=["onboarding-intermediate"]
        )
        assert len(scenarios) == 1
        s = scenarios[0]
        # user_message is mapped to prompt by the loader's normalization.
        assert s.prompt == "I just installed the agent-builder power and want to use it."
        assert s.max_turns == 12
        assert s.timeout_seconds == 600
        assert "onboarding" in s.tags
        assert s.simulated_human_guidance  # the long human-behavior script
        # Every assertion carries the fields the judge prompt needs.
        assert s.assertions
        for a in s.assertions:
            assert a["name"]
            assert a["type"]
            assert "check" in a

    def test_assertion_types_are_supported(self) -> None:
        """Sample assertion types are all types the framework knows how to grade."""
        supported = {
            "transcript_contains",
            "transcript_not_contains",
            "transcript_contains_any",
            "tool_called",
            "file_created",
            "llm_judge",
        }
        scenarios = load_scenarios(TEST_SAMPLES, validate=False)
        for s in scenarios:
            for a in s.assertions:
                assert a["type"] in supported, f"Unsupported assertion type: {a['type']}"

    def test_list_scenarios_handles_array_files(self) -> None:
        """list_scenarios summarizes samples even when the file is a JSON array."""
        summaries = list_scenarios(TEST_SAMPLES)
        ids = {s["id"] for s in summaries}
        assert "onboarding-intermediate" in ids


class TestAgentUnderTestConfig:
    """The agent-under-test wiring produces a valid EvalConfig."""

    def test_agent_dir_exists_with_mcp(self) -> None:
        assert (AGENT_UNDER_TEST / "AGENT.md").is_file()
        assert (AGENT_UNDER_TEST / "mcp.json").is_file()

    def test_config_constructs_and_detects_mcp_server(self) -> None:
        """EvalConfig construction auto-detects the agent-builder MCP server."""
        config = EvalConfig(
            agent_name="aws-transform-agent-builder",
            agent_dir=AGENT_UNDER_TEST,
            evals_dir=TEST_SAMPLES,
        )
        # __post_init__ reads agent_dir/mcp.json and records the server name.
        assert config.mcp_server_name == "agent-builder"
