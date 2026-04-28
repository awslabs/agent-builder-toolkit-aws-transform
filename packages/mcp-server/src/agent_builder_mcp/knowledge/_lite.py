"""Lightweight knowledge base using BM25 keyword search."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

DATA_DIR = Path(__file__).parent / "data"

# Source names for citations (package names)
SOURCE_NAMES = {
    "sdk": "ElasticGumbyPlatformPartnerBaseAgent",
    "agentic-api": "ElasticGumbyAgenticApiModel",
    "registry-api": "ATXAgentRegistryExternalServiceModel",
    "dev-guide": "ATX-Developer-Guide",
    "hitl-component-library": "HITL-Component-Library",
    "hitl-common-patterns": "HITL-Common-Patterns",
    "hitl-custom-components": "HITL-Custom-Components",
    "hitl-validation": "HITL-Validation",
    "hitl-generation-rules": "HITL-Generation-Rules",
    "hitl-agent-integration": "HITL-Agent-Integration",
    "hitl-sdk-python": "ElasticGumbyHITLComponentPythonSDK",
    "hitl-sdk-java": "ElasticGumbyHITLComponentJavaSDK",
    "hitl-architecture": "HITL-System-Architecture",
    "hitl-render-limitations": "HITL-Render-Engine-Limitations",
}

# Map from source key to data file
_SOURCE_FILES = {
    "dev-guide": "dev_guide.md",
    "agentic-api": "agentic_api.json",
    "registry-api": "registry_api.json",
    "sdk": "sdk_docs.json",
    "hitl-sdk-python": "hitl_sdk_python_docs.json",
    "hitl-sdk-java": "hitl_sdk_java_docs.json",
    "hitl-component-library": "hitl_component_library.md",
    "hitl-common-patterns": "hitl_common_patterns.md",
    "hitl-custom-components": "hitl_custom_components.md",
    "hitl-validation": "hitl_validation.md",
    "hitl-generation-rules": "hitl_generation_rules.md",
    "hitl-agent-integration": "hitl_agent_integration.md",
    "hitl-architecture": "hitl_system_architecture.md",
    "hitl-render-limitations": "hitl_render_engine_limitations.md",
}

_documents: Optional[List[Tuple[str, dict[str, str]]]] = None


def _chunk_text(text: str, chunk_size: int = 512) -> list[str]:
    """Split text into word-boundary chunks."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i : i + chunk_size]))
    return chunks


def _load_documents_from_data() -> list[tuple[str, dict[str, str]]]:
    """Load and chunk all raw data files into (text, metadata) pairs."""
    documents: list[tuple[str, dict[str, str]]] = []

    for source_key, filename in _SOURCE_FILES.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue

        source_name = SOURCE_NAMES.get(source_key, source_key)

        if filename.endswith(".md"):
            text = filepath.read_text(encoding="utf-8")
            for chunk in _chunk_text(text):
                documents.append((chunk, {"source": source_name, "name": source_key}))

        elif filename.endswith(".json"):
            content = json.loads(filepath.read_text(encoding="utf-8"))

            if isinstance(content, dict) and "operations" in content:
                shapes = content.get("shapes", {})
                for op_name, op_data in content["operations"].items():
                    doc_text = f"API Operation: {op_name}\n"
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

                    documents.append(
                        (doc_text, {"source": source_name, "name": op_name, "operation": op_name})
                    )

            elif isinstance(content, list):
                for item in content:
                    name = item.get("name", "unknown")
                    parts = [f"# {name}"]
                    if "docstring" in item:
                        parts.append(item["docstring"])
                    if "description" in item:
                        parts.append(item["description"])
                    if "signature" in item:
                        parts.append(f"Signature: {item['signature']}")
                    doc_text = "\n\n".join(parts)

                    for chunk in _chunk_text(doc_text):
                        documents.append((chunk, {"source": source_name, "name": name}))

    return documents


def setup_kb():
    """Initialize knowledge base by loading documents for BM25 search."""
    global _documents
    if _documents is not None:
        return
    _documents = _load_documents_from_data()


def get_documents() -> list[tuple[str, dict[str, str]]]:
    """Get loaded documents, initializing if needed."""
    setup_kb()
    assert _documents is not None
    return _documents
