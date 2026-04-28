"""Document loaders for ATX knowledge base."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from llama_index.core import Document

logger = logging.getLogger(__name__)


def load_markdown_docs(path: str) -> list[Document]:
    """Load markdown documentation."""
    logger.debug(f"Loading markdown doc from: {path}")
    with open(path) as f:
        content = f.read()
    logger.debug(f"Loaded {len(content)} characters from {path}")
    return [Document(text=content, metadata={"source": "dev-guide", "path": path})]


def load_python_sdk(path: str) -> list[Document]:
    """Extract docstrings and signatures from Python SDK."""
    logger.debug(f"Scanning Python SDK at: {path}")
    documents = []
    py_files = list(Path(path).rglob("*.py"))
    logger.debug(f"Found {len(py_files)} Python files")

    for py_file in py_files:
        try:
            with open(py_file) as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    docstring = ast.get_docstring(node) or ""
                    if docstring:
                        doc_text = f"# {node.name}\n\n{docstring}"
                        documents.append(
                            Document(
                                text=doc_text,
                                metadata={"source": "sdk", "path": str(py_file), "name": node.name},
                            )
                        )
        except (SyntaxError, UnicodeDecodeError) as e:
            logger.debug(f"Skipping {py_file}: {e}")
            continue

    logger.debug(f"Extracted {len(documents)} SDK docstrings")
    return documents


def load_api_specs(path: str) -> list[Document]:
    """Parse service-2.json into searchable documents."""
    logger.debug(f"Loading API spec from: {path}")
    with open(path) as f:
        spec = json.load(f)

    documents = []
    operations = spec.get("operations", {})
    shapes = spec.get("shapes", {})

    logger.debug(f"Processing {len(operations)} API operations")

    for op_name, op_data in operations.items():
        doc_text = f"# API Operation: {op_name}\n\n"
        doc_text += f"HTTP: {op_data.get('http', {}).get('method', '')} {op_data.get('http', {}).get('requestUri', '')}\n"

        input_shape = op_data.get("input", {}).get("shape", "")
        if input_shape and input_shape in shapes:
            doc_text += f"\nInput ({input_shape}):\n"
            for member, details in shapes[input_shape].get("members", {}).items():
                doc_text += f"  - {member}: {details.get('shape', 'unknown')}\n"

        output_shape = op_data.get("output", {}).get("shape", "")
        if output_shape and output_shape in shapes:
            doc_text += f"\nOutput ({output_shape}):\n"
            for member, details in shapes[output_shape].get("members", {}).items():
                doc_text += f"  - {member}: {details.get('shape', 'unknown')}\n"

        documents.append(Document(text=doc_text, metadata={"source": "api", "operation": op_name}))

    logger.debug(f"Created {len(documents)} API operation documents")
    return documents
