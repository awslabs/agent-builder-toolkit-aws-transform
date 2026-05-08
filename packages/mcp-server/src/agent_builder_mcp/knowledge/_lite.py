"""Lightweight knowledge base using BM25 keyword search."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import snowballstemmer
from rank_bm25 import BM25Okapi

DATA_DIR = Path(__file__).parent / "data"

# Source names for citations (package names)
SOURCE_NAMES = {
    "sdk": "AgentBuilderSDK",
    "agentic-api": "TransformAgenticApiModel",
    "registry-api": "ATXAgentRegistryExternalServiceModel",
    "dev-guide": "ATX-Developer-Guide",
    "hitl-component-library": "HITL-Component-Library",
    "hitl-common-patterns": "HITL-Common-Patterns",
    "hitl-custom-components": "HITL-Custom-Components",
    "hitl-validation": "HITL-Validation",
    "hitl-generation-rules": "HITL-Generation-Rules",
    "hitl-agent-integration": "HITL-Agent-Integration",
    "hitl-sdk-python": "TransformHITLComponentPythonSDK",
    "hitl-sdk-java": "TransformHITLComponentJavaSDK",
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

# BM25 tuning constants
BM25_K1: float = 1.2  # Term frequency saturation (lower = less advantage for repeated terms)
BM25_B: float = 0.5  # Document length normalization (lower = less penalty on longer chunks)

# BM25 index cache — populated by setup_kb(), used by search functions
_documents: Optional[List[Tuple[str, dict[str, str]]]] = None
_bm25: Optional[BM25Okapi] = None
_tokenized_corpus: Optional[list[list[str]]] = None
_kb_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Tokenizer constants
# ---------------------------------------------------------------------------

_CAMEL_RE: re.Pattern[str] = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

_stemmer_local = threading.local()


def _get_stemmer() -> snowballstemmer.basestemmer.BaseStemmer:
    """Get a thread-local stemmer instance."""
    if not hasattr(_stemmer_local, "stemmer"):
        _stemmer_local.stemmer = snowballstemmer.stemmer("english")
    return _stemmer_local.stemmer


STOP_WORDS: frozenset[str] = frozenset(
    "a an the and or but not is are was were be been being "
    "have has had do does did will would shall should may might "
    "can could to of in for on with at by from as into about "
    "between through after before above below how what which "
    "who when where why if then than so no it its this that "
    "these those my your his her our their all each every some any".split()
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 indexing and querying.

    Pipeline:
    1. Split CamelCase identifiers via ``_CAMEL_RE``
    2. Replace underscores with spaces (snake_case splitting)
    3. Lowercase the entire string
    4. Extract alphanumeric tokens via ``re.findall(r'[a-z0-9]+', ...)``
    5. Remove stop words
    6. Discard single-character tokens
    7. Apply Snowball English stemming

    Args:
        text: Raw text string (document content or query).

    Returns:
        List of normalised, stemmed tokens.
    """
    # 1. CamelCase split — insert space at boundaries
    text = _CAMEL_RE.sub(" ", text)
    # 2. Replace underscores with spaces (snake_case)
    text = text.replace("_", " ")
    # 3. Lowercase
    text = text.lower()
    # 4. Extract alphanumeric tokens
    tokens = re.findall(r"[a-z0-9]+", text)
    # 5. Remove stop words
    tokens = [t for t in tokens if t not in STOP_WORDS]
    # 6. Discard single-character tokens
    tokens = [t for t in tokens if len(t) >= 2]
    # 7. Snowball stem
    tokens = _get_stemmer().stemWords(tokens)
    return tokens


# ---------------------------------------------------------------------------
# Domain synonym map for query expansion.
# Defined in raw English; keys are stemmed and values are run through the full
# tokenize() pipeline at module load time so they match the indexed corpus.
# ---------------------------------------------------------------------------

_SYNONYMS_RAW: dict[str, list[str]] = {
    "create": ["implement", "extend", "build", "scaffold"],
    "deploy": ["publish", "register", "push", "pipeline"],
    "orchestrator": ["workflow", "coordinator", "multi", "agent", "async", "base"],
    "subagent": ["worker", "specialized", "async", "base"],
    "invoke": ["call", "trigger", "agent"],
    "error": ["exception", "failure", "traceback", "raise"],
    "test": ["validate", "verify", "assert", "pytest"],
    "config": ["configure", "settings", "environment", "env"],
    "auth": ["credentials", "iam", "role", "permission", "allowlist"],
    "log": ["cloudwatch", "debug", "trace"],
    "hitl": ["domTreeJson", "autoForm", "cloudscape", "component"],
    "api": ["operation", "endpoint", "request", "response"],
    "container": ["docker", "finch", "ecr", "image"],
    "message": ["process", "async", "invoke"],
}


def _build_synonyms(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Stem keys and tokenize values to match ``tokenize()`` output."""
    stemmer = snowballstemmer.stemmer("english")
    result: dict[str, list[str]] = {}
    for key, values in raw.items():
        stemmed_key = stemmer.stemWord(key)
        stemmed_values: list[str] = []
        for v in values:
            stemmed_values.extend(tokenize(v))
        result[stemmed_key] = stemmed_values
    return result


SYNONYMS: dict[str, list[str]] = _build_synonyms(_SYNONYMS_RAW)


def expand_query(tokens: list[str]) -> list[str]:
    """Expand query tokens with domain synonyms.

    Adds synonym tokens to improve recall without losing precision.
    BM25 IDF naturally downweights common expansion terms.

    Args:
        tokens: Tokenized (and stemmed) query tokens.

    Returns:
        Expanded token list with originals preserved.
    """
    seen: set[str] = set()
    expanded: list[str] = []
    # First pass: add original tokens preserving order
    for token in tokens:
        if token not in seen:
            seen.add(token)
            expanded.append(token)
    # Second pass: add synonym tokens not already seen
    for token in tokens:
        if token in SYNONYMS:
            for syn in SYNONYMS[token]:
                if syn not in seen:
                    seen.add(syn)
                    expanded.append(syn)
    return expanded


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 128) -> list[str]:
    """Split text into word-boundary chunks with overlap.

    Args:
        text: Raw text to chunk.
        chunk_size: Maximum words per chunk (default 512).
        overlap: Number of overlapping words between consecutive chunks (default 128).

    Returns:
        List of text chunks. Short texts return a single chunk.
        Empty text returns an empty list.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [text]

    overlap = min(overlap, chunk_size - 1)
    step = max(1, chunk_size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    return chunks


# ---------------------------------------------------------------------------
# Document loading
# ---------------------------------------------------------------------------


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
                    doc_text += (
                        f"HTTP: {op_data.get('http', {}).get('method', '')} "
                        f"{op_data.get('http', {}).get('requestUri', '')}\n"
                    )

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

                    meta: dict[str, str] = {"source": source_name, "name": name}
                    file_val = item.get("file")
                    if isinstance(file_val, str) and file_val.strip():
                        meta["file"] = file_val.strip()
                    module_val = item.get("module")
                    if isinstance(module_val, str) and module_val.strip():
                        meta["module"] = module_val.strip()
                    for chunk in _chunk_text(doc_text):
                        documents.append((chunk, meta))

    return documents


# ---------------------------------------------------------------------------
# Knowledge base initialisation and accessors
# ---------------------------------------------------------------------------


def setup_kb() -> None:
    """Initialize knowledge base: load documents, tokenize, build BM25 index."""
    global _documents, _bm25, _tokenized_corpus
    if _documents is not None:
        return
    with _kb_lock:
        if _documents is not None:
            return
        docs = _load_documents_from_data()
        corpus = [tokenize(doc) for doc, _ in docs]
        bm25 = BM25Okapi(corpus, k1=BM25_K1, b=BM25_B)
        _tokenized_corpus = corpus
        _bm25 = bm25
        _documents = docs


def get_documents() -> list[tuple[str, dict[str, str]]]:
    """Get loaded documents, initializing if needed."""
    setup_kb()
    assert _documents is not None
    return _documents


def get_bm25() -> BM25Okapi:
    """Get the cached BM25 index. Calls setup_kb() if not initialized."""
    setup_kb()
    assert _bm25 is not None
    return _bm25


def get_tokenized_corpus() -> list[list[str]]:
    """Get the cached tokenized corpus. Calls setup_kb() if not initialized."""
    setup_kb()
    assert _tokenized_corpus is not None
    return _tokenized_corpus
