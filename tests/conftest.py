# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Test configuration for top-level scripts."""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def generate_sdk_docs():
    """Import generate_sdk_docs.py as a module without sys.path manipulation."""
    spec = importlib.util.spec_from_file_location(
        "generate_sdk_docs", REPO_ROOT / "scripts" / "generate_sdk_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tmp_sdk(tmp_path):
    """Create a minimal SDK package structure for testing."""
    pkg = tmp_path / "agent_builder_sdk"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Agent Builder SDK."""\n')
    return pkg


@pytest.fixture(scope="session")
def real_sdk_path():
    """Path to the actual SDK source. Skips if not available."""
    path = REPO_ROOT / "packages" / "sdk" / "src" / "agent_builder_sdk"
    if not path.is_dir():
        pytest.skip("SDK source not available")
    return path


@pytest.fixture(scope="session")
def sdk_docs_json_path():
    """Path to the committed sdk_docs.json."""
    path = REPO_ROOT / "packages" / "mcp-server" / "src" / "agent_builder_mcp" / "knowledge" / "data" / "sdk_docs.json"
    if not path.exists():
        pytest.skip("Committed sdk_docs.json not found")
    return path
