# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Search tools using BM25 keyword search."""

import json

from ...knowledge._lite import (
    DATA_DIR,
    SOURCE_NAMES,
    expand_query,
    get_bm25,
    get_documents,
    tokenize,
)

# Maximum characters to return per search result
MAX_CONTENT_LENGTH = 500


def keyword_search(query: str, top_k: int = 5) -> str:
    """Search ATX documentation using keyword search."""
    documents = get_documents()
    bm25 = get_bm25()

    query_tokens = tokenize(query)
    # Only expand natural-language queries (multi-word), not code identifiers.
    # Single identifiers like "CreateHitlTask" get CamelCase-split by tokenize()
    # and expansion would add noise tokens that outrank the exact match.
    if " " in query.strip():
        query_tokens = expand_query(query_tokens)
    scores = bm25.get_scores(query_tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    output = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        doc, meta = documents[idx]
        result: dict[str, object] = {
            "content": doc[:MAX_CONTENT_LENGTH],
            "score": round(float(scores[idx]), 3),
            "source": meta.get("source", "unknown"),
            "citation": f"[{meta.get('source', 'unknown')}:{meta.get('name', meta.get('operation', 'doc'))}]",
        }
        if meta.get("file"):
            result["file"] = meta["file"]
        if meta.get("module"):
            result["module"] = meta["module"]
        output.append(result)
    return json.dumps(output, indent=2)


def search_by_source(query: str, source: str, top_k: int = 5) -> str:
    """Search filtered by source."""
    documents = get_documents()
    bm25 = get_bm25()

    source_name = SOURCE_NAMES.get(source, source)
    query_tokens = tokenize(query)
    # No synonym expansion for source-filtered search — the user already
    # narrowed scope, and expansion adds noise that hurts precision.

    # Query global index, then filter by source
    scores = bm25.get_scores(query_tokens)
    scored_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    output: list[dict[str, object]] = []
    for idx in scored_indices:
        if scores[idx] <= 0 or len(output) >= top_k:
            break
        doc, meta = documents[idx]
        if meta.get("source") != source_name:
            continue
        result: dict[str, object] = {
            "content": doc[:MAX_CONTENT_LENGTH],
            "score": round(float(scores[idx]), 3),
            "source": meta.get("source", "unknown"),
            "citation": f"[{meta.get('source', 'unknown')}:{meta.get('name', meta.get('operation', 'doc'))}]",
        }
        if meta.get("file"):
            result["file"] = meta["file"]
        if meta.get("module"):
            result["module"] = meta["module"]
        output.append(result)
    return json.dumps(output, indent=2)


def get_hitl_generation_prompt() -> str:
    """Get the complete HITL UI generation rules. Call this before generating domTreeJson."""
    return (DATA_DIR / "hitl_generation_rules.md").read_text()
