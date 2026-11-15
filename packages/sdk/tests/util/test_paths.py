# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the container path checks in agent_builder_sdk.util.paths."""

import os
from pathlib import Path

import pytest

from agent_builder_sdk.util import paths

_PROTECTED_AT_IMPORT = set(paths._protected)


@pytest.fixture(autouse=True)
def no_protected_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "_protected", set())


def test_is_under_follows_symlinks_and_dot_dot(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside)

    assert paths.is_under(str(root / "a" / "b.txt"), [str(root)])
    assert not paths.is_under(str(root / ".." / "outside" / "x"), [str(root)])
    assert not paths.is_under(str(root / "link" / "x"), [str(root)])


@pytest.mark.parametrize("name", ["tasks/task-1.json", "conversations.json", "memories/m1.json"])
def test_protected_runtime_state_is_refused_for_read_and_write(tmp_path: Path, name: str) -> None:
    storage = tmp_path / "agent"
    target = storage / name
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    paths.protect(str(storage))

    assert not paths.is_under(str(target), [str(tmp_path)])
    assert "runtime state" in (paths.unreadable(str(target), [str(tmp_path)]) or "")
    assert "runtime state" in (paths.unwritable(str(target), [str(tmp_path)]) or "")
    # A symlink from an allowed place into the state is refused too.
    (tmp_path / "alias.json").symlink_to(target)
    assert "runtime state" in (paths.unreadable(str(tmp_path / "alias.json"), [str(tmp_path)]) or "")
    assert paths.unreadable(str(tmp_path / "report.html"), [str(tmp_path)]) is None


def test_a_protected_file_is_refused_but_its_siblings_are_not(tmp_path: Path) -> None:
    paths.protect(str(tmp_path / "server.log"))

    assert "runtime state" in (paths.unwritable(str(tmp_path / "server.log"), [str(tmp_path)]) or "")
    assert paths.unwritable(str(tmp_path / "server.log.txt"), [str(tmp_path)]) is None


def test_an_allowed_root_inside_protected_state_stays_allowed(tmp_path: Path) -> None:
    storage = tmp_path / "agent"
    skills = storage / "downloaded_skills"
    paths.protect(str(storage))
    roots = [str(tmp_path), str(skills)]

    assert paths.is_under(str(skills / "demo" / "SKILL.md"), roots)
    assert not paths.is_under(str(storage / "conversations.json"), roots)
    # Listing the protected dir itself as a root does not make it allowed.
    assert not paths.is_under(str(storage / "conversations.json"), [str(storage)])


def test_unwritable_refuses_a_symlink_and_a_directory(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "dir")

    assert "symlink" in (paths.unwritable(str(tmp_path / "link"), [str(tmp_path)]) or "")
    assert "directory" in (paths.unwritable(str(tmp_path / "dir"), [str(tmp_path)]) or "")
    assert "not under" in (paths.unwritable("/etc/passwd", [str(tmp_path)]) or "")
    assert paths.unwritable(str(tmp_path / "new.txt"), [str(tmp_path)]) is None
    assert "directory" in (paths.unwritable(str(tmp_path / "new") + os.sep, [str(tmp_path)]) or "")


@pytest.mark.parametrize(
    ("suffix", "reason"),
    [("a/../b.txt", "'..' component"), ("a\0b.txt", "NUL byte")],
    ids=["dot dot", "nul byte"],
)
def test_a_dot_dot_component_or_a_nul_byte_is_refused(tmp_path: Path, suffix: str, reason: str) -> None:
    path = f"{tmp_path}{os.sep}{suffix}"
    assert reason in (paths.unreadable(path, [str(tmp_path)]) or "")
    assert reason in (paths.unwritable(path, [str(tmp_path)]) or "")


def test_a_sibling_that_shares_the_name_prefix_is_not_under_it(tmp_path: Path) -> None:
    assert not paths.is_under(str(tmp_path / "skills-private" / "x"), [str(tmp_path / "skills")])
    paths.protect(str(tmp_path / "agent"))
    assert paths.is_under(str(tmp_path / "agent2" / "x"), [str(tmp_path)])


def test_relative_and_symlinked_roots_and_protected_dirs_are_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    (real / "agent").mkdir(parents=True)
    (tmp_path / "link").symlink_to(real)
    monkeypatch.chdir(tmp_path)

    assert paths.is_under(str(real / "skills" / "SKILL.md"), ["./real"])
    assert paths.is_under(str(real / "x"), [str(tmp_path / "link")])
    paths.protect("./link/agent")
    assert not paths.is_under(str(real / "agent" / "conversations.json"), [str(tmp_path)])


def test_the_sdk_default_state_locations_are_protected_from_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "_protected", _PROTECTED_AT_IMPORT)

    assert "runtime state" in (paths.unwritable("/tmp/agent_state", ["/tmp"]) or "")
    assert "runtime state" in (paths.unwritable("/tmp/atx-mcp-server.log", ["/tmp"]) or "")
    assert "runtime state" in (paths.unwritable("/tmp/orchestrator_agent/conversations.json", ["/tmp"]) or "")
    assert paths.unwritable("/tmp/a-report-that-does-not-exist.md", ["/tmp"]) is None
