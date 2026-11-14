# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/check_public_refs.py."""

import os
import re
import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest

# "|" splits the address so that this file passes the check it tests.
EMAIL = "first.last@ama|zon.com".replace("|", "")


@pytest.fixture
def foreign_index(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point GIT_INDEX_FILE at a path outside the test repository, as git does for a hook."""
    index = tmp_path_factory.mktemp("caller") / "index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(index))
    return index


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty git repository that is also the current directory."""
    # git sets GIT_INDEX_FILE and GIT_DIR for hooks. With them, `git add` here would write to the caller's repository.
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
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

    def test_self_test_fails_when_any_pattern_stops_ignoring_case(
        self, check_public_refs: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rules = check_public_refs.RULES
        for rule in rules:
            if rule.pattern.flags & re.IGNORECASE:
                exact = rule._replace(pattern=re.compile(rule.pattern.pattern))
                monkeypatch.setattr(check_public_refs, "RULES", tuple(exact if r is rule else r for r in rules))
                failures = check_public_refs.failed_samples()
                assert any(entry.startswith("not flagged: ") for entry in failures), rule.name

    @pytest.mark.parametrize(("name", "anchor"), [("host", "^"), ("host", "$"), ("email", "^"), ("access key", "$")])
    def test_self_test_fails_when_an_allowlist_loses_an_anchor(
        self, check_public_refs: ModuleType, monkeypatch: pytest.MonkeyPatch, name: str, anchor: str
    ) -> None:
        rules = check_public_refs.RULES
        rule = next(rule for rule in rules if rule.name == name)
        assert anchor in rule.allowed.pattern
        loose = rule._replace(allowed=re.compile(rule.allowed.pattern.replace(anchor, ""), rule.allowed.flags))
        monkeypatch.setattr(check_public_refs, "RULES", tuple(loose if r is rule else r for r in rules))

        failures = check_public_refs.failed_samples()
        assert any(entry.startswith("not flagged: ") for entry in failures)

    def test_line_number_counts_from_one(self, check_public_refs: ModuleType) -> None:
        assert list(check_public_refs.find_refs(f"{EMAIL}\n\n{EMAIL}\n")) == [(1, "email", EMAIL), (3, "email", EMAIL)]

    def test_escaped_dots_keep_the_line_number_and_show_as_plain_dots(self, check_public_refs: ModuleType) -> None:
        escaped = EMAIL.replace(".", "\\\\.")

        assert list(check_public_refs.find_refs(f"a\\.b\n{escaped}\n")) == [(2, "email", EMAIL)]

    @pytest.mark.parametrize(("unit", "count"), [("a", 30_000), ("\\", 200_000)])
    def test_long_run_of_one_character_scans_in_linear_time(
        self, check_public_refs: ModuleType, unit: str, count: int
    ) -> None:
        # A pattern that retries from every character of the run needs tens of seconds for this input.
        start = time.process_time()
        assert list(check_public_refs.find_refs(unit * count + "%" * 30_000)) == []
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

    def test_tracked_file_missing_from_the_working_tree_raises_instead_of_passing(
        self, check_public_refs: ModuleType, repo: Path
    ) -> None:
        _track(repo, "gone.md", EMAIL.encode())
        (repo / "gone.md").unlink()

        with pytest.raises(FileNotFoundError):
            check_public_refs.main([])

    def test_reports_a_hit_in_a_path(self, check_public_refs: ModuleType, repo: Path) -> None:
        _track(repo, f"{EMAIL}/notes.md", b"clean\n")

        assert check_public_refs.scan_tracked_files() == [f"{EMAIL}/notes.md: path: email: {EMAIL}"]

    def test_scans_a_symbolic_link_as_the_path_it_holds(self, check_public_refs: ModuleType, repo: Path) -> None:
        (repo / "link").symlink_to(f"missing/{EMAIL}")
        (repo / "to-folder").symlink_to(".")
        subprocess.run(["git", "add", "link", "to-folder"], cwd=repo, check=True)

        assert check_public_refs.scan_tracked_files() == [f"link:1: email: {EMAIL}"]

    def test_scans_only_the_path_of_a_submodule(self, check_public_refs: ModuleType, repo: Path) -> None:
        for name in ("vendor/lib", f"vendor/{EMAIL}"):
            subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"160000,{'1' * 40},{name}"], check=True)

        assert check_public_refs.scan_tracked_files() == [f"vendor/{EMAIL}: path: email: {EMAIL}"]

    def test_repo_fixture_leaves_an_index_named_by_the_environment_alone(
        self, check_public_refs: ModuleType, foreign_index: Path, repo: Path
    ) -> None:
        _track(repo, "notes.md", EMAIL.encode())

        assert not foreign_index.exists()
        assert check_public_refs.scan_tracked_files() == [f"notes.md:1: email: {EMAIL}"]

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
        assert "allowlist of its rule in scripts/check_public_refs.py" in out.splitlines()[0]
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
