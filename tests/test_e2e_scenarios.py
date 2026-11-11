# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Every e2e scenario parses the way the simulated-builder runner reads it (e2e/README.md)."""

import json
import re
from pathlib import Path

import pytest

PLACEHOLDERS = {"commit", "short", "repo", "pr", "agent", "chat_label", "workspace", "archive", "pip", "pip_runtime", "mcp_from"}
REQUIRED = {"id", "title", "pr", "agent", "chat_label", "workspace", "job", "surface"}
META = re.compile(r"^```json scenario\n(.*?)\n```$", re.M | re.S)
BLOCK = re.compile(r"^```(kiro|web) ([\w-]+)\n(.*?)\n```$", re.M | re.S)
SCENARIOS = sorted((Path(__file__).resolve().parent.parent / "e2e" / "scenarios").glob("*.md"))


def test_scenarios_exist():
    assert SCENARIOS


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.name)
def test_scenario(path):
    text = path.read_text(encoding="utf-8")
    metas = META.findall(text)
    assert len(metas) == 1, "exactly one ```json scenario block"
    meta = json.loads(metas[0])
    assert REQUIRED <= meta.keys(), f"missing keys: {REQUIRED - meta.keys()}"
    assert re.fullmatch(r"[a-z0-9-]+-", meta["agent"]), "agent is a lowercase prefix ending in '-' (the runner appends the account ID)"
    blocks = BLOCK.findall(text)
    names = [n for _, n, _ in blocks]
    assert len(names) == len(set(names)), "block names are unique"
    kiro = [n for kind, n, _ in blocks if kind == "kiro"]
    assert kiro[0] == "install" and "cleanup" in kiro, "starts with kiro install, has kiro cleanup"
    assert any(kind == "web" for kind, _, _ in blocks), "at least one web block exercises the feature in a job"
    for _, n, body in blocks:
        unknown = set(re.findall(r"\{(\w+)\}", body)) - PLACEHOLDERS
        assert not unknown, f"{n}: unknown placeholders {unknown}"
        assert not re.search(r"\b\d{12}\b", body), f"{n}: no account IDs in scenarios"
    install = dict((n, b) for _, n, b in blocks)["install"]
    assert "{pip}" in install, "install takes the toolkit from the PR commit"
