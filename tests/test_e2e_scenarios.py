# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Every e2e scenario parses the way the simulated-builder runner reads it (e2e/README.md)."""

import json
import re
from pathlib import Path

import pytest

PLACEHOLDERS = {"commit", "short", "repo", "pr", "agent", "chat_label", "workspace", "archive", "pip", "pip_runtime", "mcp_from", "artifact_bucket", "build_role"}
REQUIRED = {"id", "title", "pr", "agent", "chat_label", "workspace", "job"}
META = re.compile(r"^```json scenario\n(.*?)\n```$", re.M | re.S)
BLOCK = re.compile(r"^```(kiro|web) ([\w-]+)\n(.*?)\n```$", re.M | re.S)
SCENARIOS = sorted((Path(__file__).resolve().parent.parent / "e2e" / "scenarios").glob("*.md"))


def test_scenarios_exist():
    assert SCENARIOS


def flat(s):
    """Text as the runner compares it (no commas between digits), with each run of whitespace as one space."""
    return " ".join(re.sub(r"(?<=\d),(?=\d)", "", s).split())


def check(text):
    metas = META.findall(text)
    assert len(metas) == 1, "exactly one ```json scenario block"
    meta = json.loads(metas[0])
    assert REQUIRED <= meta.keys(), f"missing keys: {REQUIRED - meta.keys()}"
    # The registry allows 30 characters for the owner name, and the toolkit sends the agent name as
    # the owner name: 12 for the account ID and a few for the runner's own suffix leave 11 here.
    assert re.fullmatch(r"[a-z0-9-]{1,11}-", meta["agent"]), "agent is a lowercase prefix of at most 11 characters, ending in '-' (the runner appends the account ID)"
    blocks = BLOCK.findall(text)
    names = [n for _, n, _ in blocks]
    assert len(names) == len(set(names)), "block names are unique"
    kiro = [n for kind, n, _ in blocks if kind == "kiro"]
    assert kiro[0] == "install" and "cleanup" in kiro, "starts with kiro install, has kiro cleanup"
    web = {n for kind, n, _ in blocks if kind == "web"}
    assert web, "at least one web block exercises the feature in a job"
    for _, n, body in blocks:
        unknown = set(re.findall(r"\{(\w+)\}", body)) - PLACEHOLDERS
        assert not unknown, f"{n}: unknown placeholders {unknown}"
        assert not re.search(r"\b\d{12}\b", body), f"{n}: no account IDs in scenarios"
    install = dict((n, b) for _, n, b in blocks)["install"]
    assert "{pip}" in install, "install takes the toolkit from the PR commit"
    chat = meta.get("chat", {})
    assert meta.get("surface") or chat, "the feature check is surface or chat (or both)"
    assert isinstance(chat, dict) and chat.keys() <= web, f"chat keys are names of web blocks: {sorted(web)}"
    checks = [(f"chat {n}", c) for n, c in chat.items()] + ([("logs", meta["logs"])] if "logs" in meta else [])
    for where, c in checks:
        assert isinstance(c, dict) and c.keys() <= {"has", "lacks"} and any(c.values()), f"{where}: has and/or lacks, with at least one string"
        for strings in c.values():
            ok = isinstance(strings, list) and all(isinstance(s, str) and s.strip() and not re.search(r"\d,\d", s) for s in strings)
            assert ok, f"{where}: lists of non-empty strings, with no comma between digits (the runner removes those)"
        for s in c.get("has", []):
            echo = [n for _, n, body in blocks if flat(s) in flat(body)]
            assert not echo, f"{where}: {s!r} is in the prompt {echo}: a value from a prompt can pass without the feature"


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.name)
def test_scenario(path):
    check(path.read_text(encoding="utf-8"))


def scenario(**checks):
    """A minimal scenario with the given feature checks."""
    meta = {"id": "x", "title": "x", "pr": 1, "agent": "x-", "chat_label": "X", "workspace": "w", "job": "j", **checks}
    ask = "Add 120,000 to the lines\nof code of the smallest app."
    blocks = {"json scenario": json.dumps(meta), "kiro install": "pip install {pip}", "web ask": ask, "kiro cleanup": "Deregister {agent}."}
    return "".join(f"```{kind}\n{body}\n```\n" for kind, body in blocks.items())


OK = {"has": ["165000"], "lacks": ["Error"]}


@pytest.mark.parametrize("checks", [
    {"chat": {"ask": OK}},
    {"surface": {"component": "Table"}, "chat": {"ask": {"lacks": ["Error"]}}, "logs": OK},
])
def test_feature_check_accepted(checks):
    check(scenario(**checks))


@pytest.mark.parametrize("checks, error", [
    ({"logs": OK}, "surface or chat"),  # logs alone is not a feature check
    ({"chat": {"install": OK}}, "web blocks"),
    ({"chat": {"ask": {"contains": ["165000"]}}}, "has and/or lacks"),
    ({"chat": {"ask": {"has": []}}}, "at least one string"),
    ({"chat": {"ask": {"has": "165000"}}}, "lists of non-empty strings"),
    ({"chat": {"ask": {"has": [""]}}}, "lists of non-empty strings"),
    ({"chat": {"ask": {"has": ["165,000"]}}}, "comma between digits"),
    ({"chat": {"ask": {"has": ["120000"]}}}, r"prompt \['ask'\]"),  # the message holds 120,000
    ({"chat": {"ask": {"has": ["lines of code"]}}}, r"prompt \['ask'\]"),  # split over two lines in the message
    ({"chat": {"ask": {"has": ["pip install"]}}}, r"prompt \['install'\]"),
    ({"chat": {"ask": OK}, "logs": {"ask": OK}}, "logs: has and/or lacks"),  # logs takes no block names
    ({"chat": {"ask": OK}, "logs": {"has": ["Deregister"]}}, r"logs: .* prompt \['cleanup'\]"),
])
def test_feature_check_rejected(checks, error):
    with pytest.raises(AssertionError, match=error):
        check(scenario(**checks))
