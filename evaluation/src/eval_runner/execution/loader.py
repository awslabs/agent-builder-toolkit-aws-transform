# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval scenario loader: scans directories, validates JSON, returns EvalCase objects.

Loads eval scenarios from a directory structure organized by migration type::

    configuration/evals/
    ├── eval-schema.json          (JSON Schema)
    ├── foundation/
    │   ├── full-dotnet-journey.json
    │   ├── skip-assessment-rejected.json
    │   └── ...
    ├── dotnet/
    │   ├── agent-selection.json
    │   └── ...
    └── custom/
        ├── td-discovery.json
        └── ...

Each JSON file is a single eval scenario validated against the schema.

Usage::

    from eval_runner.execution.loader import load_scenarios

    scenarios = load_scenarios("/path/to/evals/")
    dotnet_only = load_scenarios("/path/to/evals/", filter_tags=["dotnet"])
    single = load_scenarios("/path/to/evals/", filter_ids=["full-dotnet-journey"])
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .runner import EvalCase

logger = logging.getLogger(__name__)

# Schema filename expected at the root of the evals directory
SCHEMA_FILENAME = "eval-schema.json"


def _load_schema(evals_dir: Path) -> dict[str, Any]:
    """Load the JSON Schema, checking the evals directory first then the framework's own copy.

    Args:
        evals_dir: Root directory containing scenario subdirs.

    Returns:
        The parsed JSON Schema dict.

    Raises:
        FileNotFoundError: If ``eval-schema.json`` is not found anywhere.
    """
    # Check consumer's evals dir first, then the bundled copy under execution/data/
    candidates = [
        evals_dir / SCHEMA_FILENAME,
        Path(__file__).resolve().parent / "data" / "evals" / SCHEMA_FILENAME,
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text())
    raise FileNotFoundError(f"Schema not found in: {[str(p) for p in candidates]}")


def _normalize_scenario(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw scenario dict to the loader's expected shape.

    Mirrors the tolerant test-sample format that the test data generator emits
    (and that ``eval_runner`` consumes):

    - Drops the ``$schema`` IDE-hint key.
    - Falls back to ``user_message`` when ``prompt`` is absent.

    Unknown keys (e.g. ``complexity``, ``metadata``) are left untouched here and
    filtered out before schema validation by :func:`load_scenarios`.
    """
    data = {k: v for k, v in raw.items() if k != "$schema"}
    if "prompt" not in data and data.get("user_message"):
        data["prompt"] = data["user_message"]
    return data


def _parse_scenario(data: dict[str, Any], scenario_file: Path | None = None) -> EvalCase:
    """Parse a validated JSON dict into an EvalCase dataclass.

    Args:
        data: Validated scenario JSON data.
        scenario_file: Path to the scenario JSON file, used to resolve
            relative ``workspace_dir`` paths.

    Returns:
        An ``EvalCase`` instance.
    """
    # Resolve workspace_dir relative to the scenario JSON file.
    workspace_dir = data.get("workspace_dir")
    if workspace_dir and scenario_file:
        resolved = (scenario_file.parent / workspace_dir).resolve()
        evals_root = scenario_file.parent.resolve()
        original_root = evals_root
        while evals_root.parent != evals_root:
            if (evals_root / SCHEMA_FILENAME).exists():
                break
            evals_root = evals_root.parent
        else:
            # Schema not found — fall back to scenario's directory as boundary
            evals_root = original_root
        # Block path traversal outside the evals directory tree
        try:
            resolved.relative_to(evals_root)
        except ValueError:
            logger.warning(
                f"workspace_dir in {scenario_file.name} escapes evals directory "
                f"({resolved} is outside {evals_root}). Ignoring."
            )
            resolved = None  # type: ignore[assignment]
        workspace_dir = str(resolved) if resolved else None

    return EvalCase(
        id=data["id"],
        name=data["name"],
        prompt=data["prompt"],
        description=data["description"],
        assertions=data["assertions"],
        complexity=data.get("complexity", "medium"),
        tags=data.get("tags", []),
        targets=data.get("targets", []),
        max_turns=data.get("max_turns", 10),
        timeout_seconds=data.get("timeout_seconds", 300),
        simulated_human_guidance=data.get("simulated_human_guidance"),
        agent=data.get("agent"),
        workspace_setup=data.get("workspace_setup"),
        workspace_dir=workspace_dir,
        mocks=data.get("mocks"),
    )


def load_scenarios(
    evals_dir: str | Path,
    filter_tags: list[str] | None = None,
    filter_ids: list[str] | None = None,
    filter_target: str | None = None,
    validate: bool = True,
) -> list[EvalCase]:
    """Load eval scenarios from a directory tree.

    Recursively scans ``evals_dir`` for ``*.json`` files (excluding the schema
    file itself), validates each against the schema, and returns a list of
    ``EvalCase`` objects.

    Args:
        evals_dir: Root directory containing ``eval-schema.json`` and scenario
            subdirectories (e.g., ``foundation/``, ``dotnet/``, ``custom/``).
        filter_tags: If provided, only return scenarios that have at least one
            matching tag.
        filter_ids: If provided, only return scenarios with matching IDs.
        filter_target: If provided (``"power"`` or ``"plugin"``), only return
            scenarios compatible with that target. Scenarios with an empty
            ``targets`` list are compatible with all targets.
        validate: If True (default), validate each scenario against the JSON
            Schema. Set to False for faster loading when schema conformance
            is already guaranteed.

    Returns:
        List of ``EvalCase`` objects in a deterministic order: scenarios are
        emitted by sorted source-file path, then by their order within each
        file. This is stable for a fixed directory layout, but it is **not** an
        ID sort — renaming/adding/moving a file can change the order. Callers
        that need a scenario pinned to a fixed position (e.g. a train/val/test
        split) should select by explicit ``filter_ids`` rather than by index.

    Raises:
        FileNotFoundError: If ``evals_dir`` or the schema file doesn't exist.
        jsonschema.ValidationError: If a scenario fails schema validation.
    """
    evals_path = Path(evals_dir)
    if not evals_path.is_dir():
        raise FileNotFoundError(f"Evals directory not found: {evals_path}")

    schema = _load_schema(evals_path) if validate else None

    scenarios: list[EvalCase] = []

    # Use os.walk with followlinks=True because some build/runtime environments
    # use symlinks for subdirectories (e.g., evals/foundation → build/evals/foundation).
    # Path.rglob and os.walk(followlinks=False) don't follow directory symlinks.
    all_json_files: list[Path] = []
    for root, _dirs, files in os.walk(str(evals_path), followlinks=True):
        for f in files:
            if f.endswith(".json"):
                all_json_files.append(Path(root) / f)

    for json_file in sorted(all_json_files):
        # Skip the schema file and fixture files (workspace_dir artifacts)
        if json_file.name == SCHEMA_FILENAME:
            continue
        if "/fixtures/" in str(json_file):
            continue

        try:
            raw = json.loads(json_file.read_text())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {json_file}: {e}")
            continue

        # A file may hold a single scenario object or an array of scenarios
        # (the format emitted by the test data generator and consumed by
        # eval_runner). Normalize both to a list of dicts.
        raw_scenarios = raw if isinstance(raw, list) else [raw]

        for raw_scenario in raw_scenarios:
            data = _normalize_scenario(raw_scenario)

            if validate and schema is not None:
                import jsonschema

                # Validate only schema-known keys; tolerate extra fields such as
                # `complexity` and `metadata` that generated samples carry.
                allowed = set(schema.get("properties", {}))
                data_for_validation = {k: v for k, v in data.items() if k in allowed}
                try:
                    jsonschema.validate(instance=data_for_validation, schema=schema)
                except jsonschema.ValidationError as e:
                    logger.error(f"Schema validation failed for {json_file}: {e.message}")
                    raise

            scenario = _parse_scenario(data, scenario_file=json_file)

            # Apply filters
            if filter_ids and scenario.id not in filter_ids:
                continue
            if filter_tags and not any(t in scenario.tags for t in filter_tags):
                continue
            if (
                filter_target
                and scenario.targets
                and filter_target.lower() not in [t.lower() for t in scenario.targets]
            ):
                continue

            scenarios.append(scenario)
            logger.debug(f"Loaded scenario: {scenario.id} from {json_file}")

    return scenarios


def list_scenarios(evals_dir: str | Path) -> list[dict[str, Any]]:
    """List all available scenarios with summary info.

    Loads scenarios without validation for speed and returns a summary
    suitable for CLI display.

    Args:
        evals_dir: Root directory containing eval scenarios.

    Returns:
        List of dicts with ``id``, ``name``, ``tags``, and ``path`` for each scenario.
    """
    evals_path = Path(evals_dir)
    summaries: list[dict[str, Any]] = []

    # Use os.walk with followlinks=True because some build/runtime environments
    # use symlinks for subdirectories (e.g., evals/foundation → build/evals/foundation).
    # Path.rglob and os.walk(followlinks=False) don't follow directory symlinks.
    all_json_files: list[Path] = []
    for root, _dirs, files in os.walk(str(evals_path), followlinks=True):
        for f in files:
            if f.endswith(".json"):
                all_json_files.append(Path(root) / f)

    for json_file in sorted(all_json_files):
        if json_file.name == SCHEMA_FILENAME:
            continue
        if "/fixtures/" in str(json_file):
            continue
        try:
            raw = json.loads(json_file.read_text())
        except json.JSONDecodeError:
            continue
        # A file may hold a single scenario object or an array of scenarios
        # (the format emitted by the test data generator and consumed by
        # eval_runner). Mirror load_scenarios and handle both.
        raw_scenarios = raw if isinstance(raw, list) else [raw]
        for data in raw_scenarios:
            if not isinstance(data, dict):
                continue
            summaries.append(
                {
                    "id": data.get("id", json_file.stem),
                    "name": data.get("name", ""),
                    "tags": data.get("tags", []),
                    "targets": data.get("targets", []),
                    "path": str(json_file),
                }
            )

    return summaries
