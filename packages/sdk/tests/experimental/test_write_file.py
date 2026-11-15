# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the experimental write_file tool.

_WRITE_ROOT is patched to pytest's tmp_path, because the test temp dir may not live under /tmp.
"""

import os
import shutil
import stat
import threading
import time
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

import pytest

from agent_builder_sdk.experimental import write_file as write_file_module
from agent_builder_sdk.experimental.write_file import _MAX_WRITE_BYTES, write_file
from agent_builder_sdk.util import paths

pytestmark = pytest.mark.filterwarnings("ignore::FutureWarning")


@pytest.fixture(autouse=True)
def rooted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(paths, "_protected", set())
    with mock.patch.object(write_file_module, "_WRITE_ROOT", str(tmp_path)):
        yield


def test_writes_content_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "plan.html"
    html = '<style>body{font-family:sans-serif;margin:0} /* it\'s fine */</style>\n$HOME `x` "q"'
    result = write_file(path=str(target), content=html)
    assert result == f"Wrote {len(html.encode())} bytes to {target} (file is now {len(html.encode())} bytes)."
    assert target.read_text() == html


def test_append_adds_to_the_end_and_overwrite_replaces(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    write_file(path=str(target), content="part1\n")
    result = write_file(path=str(target), content="part2\n", append=True)
    assert result.startswith("Appended 6 bytes") and result.endswith("(file is now 12 bytes).")
    assert target.read_text() == "part1\npart2\n"

    write_file(path=str(target), content="new")
    assert target.read_text() == "new"


def test_append_to_a_missing_file_creates_it(tmp_path: Path) -> None:
    target = tmp_path / "fresh.txt"
    assert write_file(path=str(target), content="x", append=True).startswith("Appended")
    assert target.read_text() == "x"


def test_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "out.txt"
    assert write_file(path=str(target), content="x").startswith("Wrote")
    assert target.read_text() == "x"


def test_an_overwrite_keeps_the_file_mode_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "run.sh"
    target.write_text("old")
    target.chmod(0o750)
    write_file(path=str(target), content="new")
    assert stat.S_IMODE(target.stat().st_mode) == 0o750
    assert os.listdir(tmp_path) == ["run.sh"]


def test_a_failed_write_leaves_the_old_file_whole(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("old content")
    with mock.patch.object(write_file_module.os, "replace", side_effect=OSError("disk full")):
        result = write_file(path=str(target), content="new content")
    assert result == f"Error: could not write {target}: disk full"
    assert target.read_text() == "old content"
    assert os.listdir(tmp_path) == ["report.txt"]


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/etc/passwd", "is not under"),
        ("relative/out.txt", "must be absolute"),
        ("{root}/a/../b.txt", "'..' component"),
        ("{root}/../escape.txt", "'..' component"),
        ("{root}/a\0b.txt", "NUL byte"),
        ("{root}", "is a directory"),
        ("{root}/sub/", "is a directory"),
        ("", "path cannot be empty"),
        ("   ", "path cannot be empty"),
    ],
    ids=["outside", "relative", "dot dot inside", "dot dot escape", "nul", "root", "trailing sep", "empty", "blank"],
)
def test_a_refused_path_writes_nothing(tmp_path: Path, path: str, reason: str) -> None:
    result = write_file(path=path.format(root=tmp_path), content="x")
    assert result.startswith("Error:") and reason in result
    assert os.listdir(tmp_path) == []


def test_a_symlink_planted_inside_the_root_cannot_redirect_a_write_outside(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "victim.txt").write_text("keep")
    (root / "dir_link").symlink_to(outside)
    (root / "file_link").symlink_to(outside / "victim.txt")

    with mock.patch.object(write_file_module, "_WRITE_ROOT", str(root)):
        assert "is not under" in write_file(path=str(root / "dir_link" / "victim.txt"), content="x")
        assert "is not under" in write_file(path=str(root / "dir_link" / "new.txt"), content="x")
        assert "is not under" in write_file(path=str(root / "file_link"), content="x", append=True)
    assert (outside / "victim.txt").read_text() == "keep"
    assert os.listdir(outside) == ["victim.txt"]


def test_a_symlink_to_a_file_inside_the_root_is_refused(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("keep")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    assert "is a symlink" in write_file(path=str(tmp_path / "link.txt"), content="x")
    assert (tmp_path / "real.txt").read_text() == "keep"


def test_oversize_content_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    target = tmp_path / "new" / "big.txt"
    result = write_file(path=str(target), content="a" * (_MAX_WRITE_BYTES + 1))
    assert "append=True" in result
    assert os.listdir(tmp_path) == []


def test_the_cap_counts_utf8_bytes_not_characters(tmp_path: Path) -> None:
    target = tmp_path / "wide.txt"
    assert "max" in write_file(path=str(target), content="é" * (_MAX_WRITE_BYTES // 2 + 1))
    assert not target.exists()


def test_content_of_exactly_the_cap_is_written(tmp_path: Path) -> None:
    target = tmp_path / "cap.txt"
    result = write_file(path=str(target), content="a" * _MAX_WRITE_BYTES)
    assert result.startswith("Wrote") and target.stat().st_size == _MAX_WRITE_BYTES


@pytest.mark.parametrize("name", ["tasks/t1.json", "conversations.json", "memories/m.json"])
def test_runtime_state_is_not_overwritten(tmp_path: Path, name: str) -> None:
    target = tmp_path / "agent" / name
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    paths.protect(str(tmp_path / "agent"))
    assert "runtime state" in write_file(path=str(target), content="x")
    assert "runtime state" in write_file(path=str(target), content="x", append=True)
    assert target.read_text() == "{}"


def test_concurrent_appends_to_one_file_all_land(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    target.write_text("start\n")
    copy = shutil.copyfileobj

    def slow_copy(src: Any, dst: Any) -> None:
        # Holds each append between its read of the old file and its rename, so unserialized
        # appends would overlap and one would be lost.
        copy(src, dst)
        time.sleep(0.1)

    with mock.patch.object(write_file_module.shutil, "copyfileobj", side_effect=slow_copy):
        threads = [
            threading.Thread(target=write_file, kwargs={"path": str(target), "content": line, "append": True})
            for line in ("a\n", "b\n")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert sorted(target.read_text().splitlines()) == ["a", "b", "start"]


def test_the_tool_spec_exposes_path_content_and_append() -> None:
    schema = write_file.tool_spec["inputSchema"]["json"]
    assert set(schema["properties"]) == {"path", "content", "append"}
    assert set(schema["required"]) == {"path", "content"}
