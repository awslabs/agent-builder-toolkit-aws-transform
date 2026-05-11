# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/generate_sdk_docs.py."""

import json
import textwrap
from pathlib import Path


def _write_module(pkg: Path, name: str, content: str) -> Path:
    """Write a Python module into the test SDK package."""
    filepath = pkg / name
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(textwrap.dedent(content))
    return filepath


class TestFunctionExtraction:
    """Test extraction of top-level functions."""

    def test_extracts_public_function(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "utils.py",
            '''\
            def hello(name: str, greeting: str = "Hi") -> str:
                """Say hello to someone.

                Args:
                    name: The person's name
                    greeting: Optional greeting prefix

                Returns:
                    The greeting string
                """
                return f"{greeting}, {name}"
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["name"] == "hello"
        assert entry["kind"] == "function"
        assert entry["file"] == "agent_builder_sdk/utils.py"
        assert entry["module"] == "agent_builder_sdk.utils"
        assert "Say hello" in entry["docstring"]
        assert "name: str" in entry["signature"]
        assert "greeting: str = 'Hi'" in entry["signature"]
        assert "-> str" in entry["signature"]
        assert "name" in entry["description"]
        assert "required" in entry["description"]

    def test_skips_private_functions(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "internal.py",
            '''\
            def _private_helper():
                """Should not appear."""
                pass

            def public_fn():
                """Should appear."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        names = [e["name"] for e in entries]
        assert "_private_helper" not in names
        assert "public_fn" in names

    def test_async_function(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "async_mod.py",
            '''\
            async def fetch_data(url: str) -> dict:
                """Fetch data from URL."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert len(entries) == 1
        assert entries[0]["signature"].startswith("async fetch_data")

    def test_function_without_docstring(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "nodoc.py",
            '''\
            def no_docs(x: int) -> int:
                return x + 1
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert len(entries) == 1
        assert entries[0]["docstring"] == ""
        assert "x: int" in entries[0]["signature"]


class TestClassExtraction:
    """Test extraction of classes and their methods."""

    def test_extracts_class_with_methods(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "agent.py",
            '''\
            class MyAgent:
                """An example agent.

                Does cool things.
                """

                def __init__(self, name: str, timeout: int = 30):
                    """Initialize the agent.

                    Args:
                        name: Agent name
                        timeout: Request timeout in seconds
                    """
                    self.name = name
                    self.timeout = timeout

                def process(self, message: str) -> str:
                    """Process a message."""
                    return message

                async def process_async(self, message: str) -> str:
                    """Process a message asynchronously."""
                    return message

                def _internal(self):
                    """Private, should not appear."""
                    pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        names = [e["name"] for e in entries]

        # Class entry
        assert "MyAgent" in names
        cls_entry = next(e for e in entries if e["name"] == "MyAgent")
        assert cls_entry["kind"] == "class"
        assert "An example agent" in cls_entry["docstring"]
        assert "name: str" in cls_entry["signature"]
        assert "timeout: int = 30" in cls_entry["signature"]
        assert "name" in cls_entry["description"]
        assert "process" in cls_entry["description"]
        assert "process_async" in cls_entry["description"]

        # Method entries
        assert "MyAgent.process" in names
        assert "MyAgent.process_async" in names
        assert "MyAgent._internal" not in names

    def test_skips_private_classes(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "private.py",
            '''\
            class _InternalHelper:
                """Should not be extracted."""
                pass

            class PublicClass:
                """Should be extracted."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        names = [e["name"] for e in entries]
        assert "_InternalHelper" not in names
        assert "PublicClass" in names

    def test_class_with_inheritance(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "derived.py",
            '''\
            class ChildAgent(BaseAgent, Mixin):
                """A derived agent."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert "Extends: BaseAgent, Mixin" in entries[0]["description"]


class TestSignatureFormatting:
    """Test _format_signature edge cases."""

    def test_kwargs(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "kw.py",
            '''\
            def configure(**kwargs) -> None:
                """Accept keyword args."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert "**kwargs" in entries[0]["signature"]

    def test_args_and_kwargs(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "mixed.py",
            '''\
            def mixed(pos: str, *args: int, key: bool = False, **kwargs) -> None:
                """Mixed args."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        sig = entries[0]["signature"]
        assert "pos: str" in sig
        assert "*args: int" in sig
        assert "key: bool = False" in sig
        assert "**kwargs" in sig

    def test_keyword_only_args(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "kwonly.py",
            '''\
            def strict(*, required_kw: str, optional_kw: int = 0) -> None:
                """Keyword-only args."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        sig = entries[0]["signature"]
        assert "required_kw: str" in sig
        assert "optional_kw: int = 0" in sig


class TestParameterExtraction:
    """Test docstring parameter parsing."""

    def test_google_style_args_section(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "params.py",
            '''\
            def create_agent(name: str, model_id: str = "default") -> None:
                """Create a new agent.

                Args:
                    name: The agent's display name
                    model_id: The foundation model to use

                Returns:
                    None
                """
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        desc = entries[0]["description"]
        assert "The agent's display name" in desc
        assert "The foundation model to use" in desc

    def test_multiline_param_description(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "multi.py",
            '''\
            def process(config: dict) -> None:
                """Process with config.

                Args:
                    config: The configuration dictionary
                        that spans multiple lines

                Returns:
                    None
                """
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        desc = entries[0]["description"]
        assert "configuration dictionary" in desc
        assert "multiple lines" in desc


class TestFileHandling:
    """Test file traversal and edge cases."""

    def test_skips_small_init_files(self, generate_sdk_docs, tmp_sdk):
        (tmp_sdk / "__init__.py").write_text("")
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        init_entries = [e for e in entries if "__init__" in e.get("file", "")]
        assert len(init_entries) == 0

    def test_handles_syntax_errors(self, generate_sdk_docs, tmp_sdk):
        _write_module(tmp_sdk, "broken.py", "def broken(:\n")
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        assert entries == []

    def test_handles_subpackages(self, generate_sdk_docs, tmp_sdk):
        sub = tmp_sdk / "subpkg"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        _write_module(
            tmp_sdk,
            "subpkg/worker.py",
            '''\
            def do_work() -> None:
                """Do some work."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        entry = next(e for e in entries if e["name"] == "do_work")
        assert "subpkg/worker.py" in entry["file"]
        assert "subpkg.worker" in entry["module"]


class TestOutputFormat:
    """Test the overall output structure and sort stability."""

    def test_output_sorted_by_file_then_name(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "z_module.py",
            '''\
            def zebra():
                """Z."""
                pass

            def alpha():
                """A."""
                pass
            ''',
        )
        _write_module(
            tmp_sdk,
            "a_module.py",
            '''\
            def beta():
                """B."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        entries.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))
        files = [e["file"] for e in entries]
        a_idx = next(i for i, f in enumerate(files) if "a_module" in f)
        z_idx = next(i for i, f in enumerate(files) if "z_module" in f)
        assert a_idx < z_idx

    def test_entry_has_required_keys(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "schema_test.py",
            '''\
            def example(x: int) -> str:
                """An example function."""
                pass
            ''',
        )
        entries = generate_sdk_docs.extract_sdk(tmp_sdk)
        entry = entries[0]
        expected_keys = {"name", "kind", "file", "module", "docstring", "signature", "description"}
        assert set(entry.keys()) == expected_keys
        assert entry["kind"] in ("class", "function", "method")

    def test_deterministic_output(self, generate_sdk_docs, tmp_sdk):
        _write_module(
            tmp_sdk,
            "stable.py",
            '''\
            class Foo:
                """Foo class."""
                def bar(self) -> None:
                    """Bar method."""
                    pass

            def baz() -> None:
                """Baz function."""
                pass
            ''',
        )
        entries_1 = generate_sdk_docs.extract_sdk(tmp_sdk)
        entries_1.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))
        entries_2 = generate_sdk_docs.extract_sdk(tmp_sdk)
        entries_2.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))
        assert entries_1 == entries_2


class TestRealSDK:
    """Smoke tests against the actual SDK source."""

    def test_extracts_core_classes(self, generate_sdk_docs, real_sdk_path):
        entries = generate_sdk_docs.extract_sdk(real_sdk_path)
        names = [e["name"] for e in entries]
        assert any("Agent" in n for n in names)
        assert len(entries) > 100

    def test_no_empty_names(self, generate_sdk_docs, real_sdk_path):
        entries = generate_sdk_docs.extract_sdk(real_sdk_path)
        for entry in entries:
            assert entry["name"], f"Empty name in {entry.get('file')}"

    def test_output_roundtrips_through_json(self, generate_sdk_docs, real_sdk_path, tmp_path):
        entries = generate_sdk_docs.extract_sdk(real_sdk_path)
        entries.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))
        output = tmp_path / "sdk_docs.json"
        output.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
        reloaded = json.loads(output.read_text())
        assert len(reloaded) == len(entries)
        assert reloaded[0] == entries[0]

    def test_committed_file_matches_generator(self, generate_sdk_docs, real_sdk_path, sdk_docs_json_path):
        """The committed sdk_docs.json must match what the generator produces."""
        entries = generate_sdk_docs.extract_sdk(real_sdk_path)
        entries.sort(key=lambda e: (e.get("file", ""), e.get("name", "")))
        generated = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
        committed_content = sdk_docs_json_path.read_text(encoding="utf-8")
        assert generated == committed_content, (
            "sdk_docs.json is stale. Run: python scripts/generate_sdk_docs.py"
        )
