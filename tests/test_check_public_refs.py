# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/check_public_refs.py."""

import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest

# "|" splits the address so that this file passes the check it tests.
EMAIL = "first.last@ama|zon.com".replace("|", "")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty git repository that is also the current directory."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _track(repo: Path, name: str, content: bytes) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    subprocess.run(["git", "add", name], cwd=repo, check=True)


class TestRules:
    def test_samples_are_judged_correctly(self, check_public_refs: ModuleType) -> None:
        assert check_public_refs.failed_samples() == []

    def test_self_test_fails_when_any_rule_is_removed(
        self, check_public_refs: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rules = check_public_refs.RULES
        for removed in rules:
            monkeypatch.setattr(check_public_refs, "RULES", tuple(rule for rule in rules if rule is not removed))
            failures = check_public_refs.failed_samples()
            assert any(entry.startswith("not flagged: ") for entry in failures), removed.name

    def test_self_test_fails_when_any_allowlist_is_removed(
        self, check_public_refs: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rules = check_public_refs.RULES
        for index, rule in enumerate(rules):
            if rule.allowed:
                changed = rules[:index] + (rule._replace(allowed=None),) + rules[index + 1 :]
                monkeypatch.setattr(check_public_refs, "RULES", changed)
                failures = check_public_refs.failed_samples()
                assert any(entry.startswith("flagged: ") for entry in failures), rule.name

    def test_line_number_counts_from_one(self, check_public_refs: ModuleType) -> None:
        assert list(check_public_refs.find_refs(f"{EMAIL}\n\n{EMAIL}\n")) == [(1, "email", EMAIL), (3, "email", EMAIL)]

    def test_long_run_of_host_characters_scans_in_linear_time(self, check_public_refs: ModuleType) -> None:
        # A pattern that retries from every character of the run needs tens of seconds for this input.
        start = time.process_time()
        assert list(check_public_refs.find_refs("a" * 30_000 + "%" * 30_000)) == []
        assert time.process_time() - start < 2


class TestScan:
    def test_reports_path_line_rule_and_match_of_tracked_files_only(
        self, check_public_refs: ModuleType, repo: Path
    ) -> None:
        _track(repo, "docs/notes.md", f"first line\ncontact {EMAIL} today\n".encode())
        _track(repo, "clean.md", "\n".join(check_public_refs.ALLOWED_SAMPLES).encode())
        (repo / "untracked.md").write_text(EMAIL)

        assert check_public_refs.scan_tracked_files() == [f"docs/notes.md:2: email: {EMAIL}"]

    def test_scans_binary_files_as_text(self, check_public_refs: ModuleType, repo: Path) -> None:
        _track(repo, "logo.png", b"\x89PNG\x00\xff\xfe" + EMAIL.encode() + b"\x00")

        assert check_public_refs.scan_tracked_files() == [f"logo.png:1: email: {EMAIL}"]

    def test_covers_the_whole_repository_from_a_subdirectory(
        self, check_public_refs: ModuleType, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _track(repo, "top.md", EMAIL.encode())
        _track(repo, "sub/inner.md", EMAIL.encode())
        monkeypatch.chdir(repo / "sub")

        assert sorted(check_public_refs.scan_tracked_files()) == [
            f"../top.md:1: email: {EMAIL}",
            f"inner.md:1: email: {EMAIL}",
        ]

    def test_skips_a_tracked_file_deleted_from_the_working_tree(
        self, check_public_refs: ModuleType, repo: Path
    ) -> None:
        _track(repo, "gone.md", EMAIL.encode())
        (repo / "gone.md").unlink()

        assert check_public_refs.scan_tracked_files() == []

    def test_git_failure_raises_instead_of_passing(
        self, check_public_refs: ModuleType, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GIT_DIR", str(repo / "missing"))

        with pytest.raises(subprocess.CalledProcessError):
            check_public_refs.main([])


class TestMain:
    def test_clean_repository_exits_zero(
        self, check_public_refs: ModuleType, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _track(repo, "clean.md", b"nothing to see\n")

        assert check_public_refs.main([]) == 0
        assert "::error::" not in capsys.readouterr().out

    def test_hit_exits_one_and_lists_it(
        self, check_public_refs: ModuleType, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _track(repo, "notes.md", EMAIL.encode())

        assert check_public_refs.main([]) == 1
        out = capsys.readouterr().out
        assert out.startswith("::error::")
        assert f"notes.md:1: email: {EMAIL}" in out.splitlines()

    def test_self_test_exits_zero_without_reading_the_repository(
        self, check_public_refs: ModuleType, repo: Path
    ) -> None:
        _track(repo, "notes.md", EMAIL.encode())

        assert check_public_refs.main(["--self-test"]) == 0

    def test_self_test_exits_one_and_lists_the_failed_samples(
        self, check_public_refs: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(check_public_refs, "RULES", ())

        assert check_public_refs.main(["--self-test"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0].startswith("::error::")
        assert out[1:] == [f"not flagged: {sample}" for sample in check_public_refs.FLAGGED_SAMPLES]
