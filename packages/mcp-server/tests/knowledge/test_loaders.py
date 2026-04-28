"""Unit tests for document loaders.

Note: loaders.py imports llama_index.core.Document at module level, which is an
optional dependency not available in the Brazil test environment. We mock it at
sys.modules level before importing the loaders module. This is a workaround until
loaders.py is refactored to use lazy imports.
"""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch


class TestLoadMarkdownDocs:
    """Tests for load_markdown_docs function."""

    def test_load_markdown_docs_returns_document(self) -> None:
        """Test loading markdown file returns Document."""
        mock_doc_class = MagicMock()
        mock_doc_instance = MagicMock()
        mock_doc_class.return_value = mock_doc_instance

        mock_llama = MagicMock()
        mock_llama.Document = mock_doc_class

        with patch.dict(sys.modules, {"llama_index.core": mock_llama}):
            # Force reimport with mocked module
            if "agent_builder_mcp.knowledge.loaders" in sys.modules:
                del sys.modules["agent_builder_mcp.knowledge.loaders"]

            from agent_builder_mcp.knowledge.loaders import (
                load_markdown_docs,
            )

            with TemporaryDirectory() as tmpdir:
                md_path = Path(tmpdir) / "test.md"
                md_path.write_text("# Test\n\nContent here")

                result = load_markdown_docs(str(md_path))

                assert len(result) == 1
                mock_doc_class.assert_called_once()
                call_kwargs = mock_doc_class.call_args[1]
                assert "# Test\n\nContent here" in call_kwargs["text"]
                assert call_kwargs["metadata"]["source"] == "dev-guide"


class TestLoadApiSpecs:
    """Tests for load_api_specs function."""

    def test_load_api_specs_parses_operations(self) -> None:
        """Test parsing API spec with operations."""
        mock_doc_class = MagicMock()
        mock_llama = MagicMock()
        mock_llama.Document = mock_doc_class

        with patch.dict(sys.modules, {"llama_index.core": mock_llama}):
            if "agent_builder_mcp.knowledge.loaders" in sys.modules:
                del sys.modules["agent_builder_mcp.knowledge.loaders"]

            from agent_builder_mcp.knowledge.loaders import (
                load_api_specs,
            )

            spec = {
                "operations": {
                    "CreateSession": {
                        "http": {"method": "POST", "requestUri": "/sessions"},
                        "input": {"shape": "CreateSessionRequest"},
                        "output": {"shape": "CreateSessionResponse"},
                    }
                },
                "shapes": {
                    "CreateSessionRequest": {"members": {"agentId": {"shape": "String"}}},
                    "CreateSessionResponse": {"members": {"sessionId": {"shape": "String"}}},
                },
            }

            with TemporaryDirectory() as tmpdir:
                spec_path = Path(tmpdir) / "api.json"
                spec_path.write_text(json.dumps(spec))

                result = load_api_specs(str(spec_path))

                assert len(result) == 1
                call_kwargs = mock_doc_class.call_args[1]
                assert "CreateSession" in call_kwargs["text"]
                assert "POST" in call_kwargs["text"]

    def test_load_api_specs_empty_operations(self) -> None:
        """Test parsing API spec with no operations."""
        mock_llama = MagicMock()
        mock_llama.Document = MagicMock()

        with patch.dict(sys.modules, {"llama_index.core": mock_llama}):
            if "agent_builder_mcp.knowledge.loaders" in sys.modules:
                del sys.modules["agent_builder_mcp.knowledge.loaders"]

            from agent_builder_mcp.knowledge.loaders import (
                load_api_specs,
            )

            spec = {"operations": {}, "shapes": {}}

            with TemporaryDirectory() as tmpdir:
                spec_path = Path(tmpdir) / "api.json"
                spec_path.write_text(json.dumps(spec))

                result = load_api_specs(str(spec_path))
                assert len(result) == 0


class TestLoadPythonSdk:
    """Tests for load_python_sdk function."""

    def test_load_python_sdk_extracts_docstrings(self) -> None:
        """Test extracting docstrings from Python files."""
        mock_doc_class = MagicMock()
        mock_llama = MagicMock()
        mock_llama.Document = mock_doc_class

        with patch.dict(sys.modules, {"llama_index.core": mock_llama}):
            if "agent_builder_mcp.knowledge.loaders" in sys.modules:
                del sys.modules["agent_builder_mcp.knowledge.loaders"]

            from agent_builder_mcp.knowledge.loaders import (
                load_python_sdk,
            )

            py_content = '''
class MyClass:
    """Class docstring."""
    pass

def my_function():
    """Function docstring."""
    pass
'''
            with TemporaryDirectory() as tmpdir:
                py_path = Path(tmpdir) / "module.py"
                py_path.write_text(py_content)

                result = load_python_sdk(tmpdir)
                assert len(result) == 2

    def test_load_python_sdk_handles_syntax_error(self) -> None:
        """Test that syntax errors are handled gracefully."""
        mock_llama = MagicMock()
        mock_llama.Document = MagicMock()

        with patch.dict(sys.modules, {"llama_index.core": mock_llama}):
            if "agent_builder_mcp.knowledge.loaders" in sys.modules:
                del sys.modules["agent_builder_mcp.knowledge.loaders"]

            from agent_builder_mcp.knowledge.loaders import (
                load_python_sdk,
            )

            with TemporaryDirectory() as tmpdir:
                py_path = Path(tmpdir) / "bad.py"
                py_path.write_text("def broken(")

                result = load_python_sdk(tmpdir)
                assert result == []
