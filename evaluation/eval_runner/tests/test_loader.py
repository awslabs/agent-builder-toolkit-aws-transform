# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the eval scenario loader."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from eval_runner.execution.loader import list_scenarios, load_scenarios

# jsonschema pulls in the rpds native extension, which isn't available on every
# platform; probe for it so schema-dependent tests can skip cleanly.
_HAS_JSONSCHEMA = importlib.util.find_spec("jsonschema") is not None

needs_jsonschema = pytest.mark.skipif(
    not _HAS_JSONSCHEMA, reason="jsonschema (rpds native ext) not available on this platform"
)


@pytest.fixture()
def evals_dir(tmp_path: Path) -> Path:
    """Create a temporary evals directory with schema and sample scenarios."""
    # Copy the real schema from the bundled execution data dir.
    schema_src = (
        Path(__file__).resolve().parent.parent
        / "execution"
        / "data"
        / "evals"
        / "eval-schema.json"
    )
    schema_dest = tmp_path / "eval-schema.json"
    schema_dest.write_text(schema_src.read_text())

    # Create foundation dir with a valid scenario
    foundation = tmp_path / "foundation"
    foundation.mkdir()
    (foundation / "test-scenario.json").write_text(
        json.dumps(
            {
                "id": "test-scenario",
                "name": "Test Scenario",
                "prompt": "Hello power",
                "description": "Test the power",
                "tags": ["foundation", "test"],
                "max_turns": 5,
                "assertions": [
                    {
                        "name": "checks_output",
                        "type": "transcript_contains",
                        "description": "Agent says hello",
                        "check": "hello",
                    }
                ],
            }
        )
    )

    # Create dotnet dir with another scenario
    dotnet = tmp_path / "dotnet"
    dotnet.mkdir()
    (dotnet / "dotnet-test.json").write_text(
        json.dumps(
            {
                "id": "dotnet-test",
                "name": ".NET Test",
                "prompt": "Modernize my .NET app",
                "description": "User wants .NET modernization",
                "tags": ["dotnet"],
                "assertions": [
                    {
                        "name": "selects_agent",
                        "type": "transcript_contains_any",
                        "description": "Selects .NET agent",
                        "check": ["dotnet", "net-refactor"],
                    }
                ],
            }
        )
    )

    return tmp_path


class TestLoadScenarios:
    """Tests for load_scenarios."""

    def test_loads_all_scenarios(self, evals_dir: Path) -> None:
        """Loads all scenarios from subdirectories."""
        scenarios = load_scenarios(evals_dir, validate=False)
        assert len(scenarios) == 2
        ids = {s.id for s in scenarios}
        assert ids == {"test-scenario", "dotnet-test"}

    def test_filters_by_tags(self, evals_dir: Path) -> None:
        """Only returns scenarios matching the tag filter."""
        scenarios = load_scenarios(evals_dir, validate=False, filter_tags=["dotnet"])
        assert len(scenarios) == 1
        assert scenarios[0].id == "dotnet-test"

    def test_filters_by_ids(self, evals_dir: Path) -> None:
        """Only returns scenarios matching the ID filter."""
        scenarios = load_scenarios(evals_dir, validate=False, filter_ids=["test-scenario"])
        assert len(scenarios) == 1
        assert scenarios[0].id == "test-scenario"

    def test_parses_all_fields(self, evals_dir: Path) -> None:
        """Correctly parses all EvalCase fields."""
        scenarios = load_scenarios(evals_dir, validate=False, filter_ids=["test-scenario"])
        s = scenarios[0]
        assert s.name == "Test Scenario"
        assert s.prompt == "Hello power"
        assert s.description == "Test the power"
        assert s.tags == ["foundation", "test"]
        assert s.max_turns == 5
        assert len(s.assertions) == 1
        assert s.assertions[0]["name"] == "checks_output"

    def test_defaults_applied(self, evals_dir: Path) -> None:
        """Missing optional fields get defaults."""
        scenarios = load_scenarios(evals_dir, validate=False, filter_ids=["dotnet-test"])
        s = scenarios[0]
        assert s.max_turns == 10  # default
        assert s.timeout_seconds == 300  # default
        assert s.agent is None  # default (set from EvalConfig at runtime)
        assert s.simulated_human_guidance is None

    def test_sorted_by_id(self, evals_dir: Path) -> None:
        """Scenarios are returned sorted by ID."""
        scenarios = load_scenarios(evals_dir, validate=False)
        assert scenarios[0].id == "dotnet-test"
        assert scenarios[1].id == "test-scenario"

    def test_skips_schema_file(self, evals_dir: Path) -> None:
        """The eval-schema.json file is not loaded as a scenario."""
        scenarios = load_scenarios(evals_dir, validate=False)
        ids = {s.id for s in scenarios}
        assert "eval-schema" not in ids

    def test_rejects_invalid_json(self, evals_dir: Path) -> None:
        """Invalid JSON files are skipped with a warning."""
        bad_file = evals_dir / "foundation" / "bad.json"
        bad_file.write_text("not json{{{")
        # Should still load the valid ones
        scenarios = load_scenarios(evals_dir, validate=False)
        assert len(scenarios) == 2

    @needs_jsonschema
    def test_rejects_schema_violation(self, evals_dir: Path) -> None:
        """Schema validation errors are raised."""
        bad_file = evals_dir / "foundation" / "missing-fields.json"
        bad_file.write_text(json.dumps({"id": "bad", "name": "Bad"}))
        with pytest.raises(Exception):  # jsonschema.ValidationError
            load_scenarios(evals_dir)

    def test_workspace_dir_resolved_relative_to_scenario(self, evals_dir: Path) -> None:
        """workspace_dir is resolved relative to the scenario JSON file."""
        scenario_file = evals_dir / "foundation" / "ws-scenario.json"
        scenario_file.write_text(
            json.dumps(
                {
                    "id": "ws-test",
                    "name": "WS",
                    "prompt": "p",
                    "description": "d",
                    "assertions": [],
                    "workspace_dir": "../fixtures/my_workspace",
                }
            )
        )
        scenarios = load_scenarios(evals_dir, validate=False, filter_ids=["ws-test"])
        expected = str((scenario_file.parent / "../fixtures/my_workspace").resolve())
        assert scenarios[0].workspace_dir == expected

    def test_skips_fixtures_directory(self, evals_dir: Path) -> None:
        """JSON files inside a fixtures/ subdirectory are not loaded."""
        fixtures_dir = evals_dir / "foundation" / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        (fixtures_dir / "helper.json").write_text(
            json.dumps(
                {
                    "id": "fixture-file",
                    "name": "Fixture",
                    "prompt": "p",
                    "description": "d",
                    "assertions": [],
                }
            )
        )
        scenarios = load_scenarios(evals_dir, validate=False)
        ids = {s.id for s in scenarios}
        assert "fixture-file" not in ids

    def test_missing_dir_raises(self) -> None:
        """FileNotFoundError for non-existent directory."""
        with pytest.raises(FileNotFoundError):
            load_scenarios("/nonexistent/path")

    def test_no_validate_mode(self, evals_dir: Path) -> None:
        """Can skip validation for faster loading."""
        scenarios = load_scenarios(evals_dir, validate=False)
        assert len(scenarios) == 2


class TestListScenarios:
    """Tests for list_scenarios."""

    def test_lists_all(self, evals_dir: Path) -> None:
        """Returns summary info for all scenarios."""
        summaries = list_scenarios(evals_dir)
        assert len(summaries) == 2
        ids = {s["id"] for s in summaries}
        assert ids == {"test-scenario", "dotnet-test"}

    def test_includes_path(self, evals_dir: Path) -> None:
        """Summary includes relative path."""
        summaries = list_scenarios(evals_dir)
        paths = {s["path"] for s in summaries}
        assert any("foundation" in p for p in paths)
        assert any("dotnet" in p for p in paths)


@needs_jsonschema
class TestRealSchemaValidation:
    """Tests that the eval schema itself is valid."""

    def test_schema_file_exists(self) -> None:
        """The eval-schema.json ships bundled under execution/data/evals/."""
        evals_dir = Path(__file__).resolve().parent.parent / "execution" / "data" / "evals"
        if not evals_dir.exists():
            pytest.skip("Evals directory not found")
        assert (evals_dir / "eval-schema.json").exists()
