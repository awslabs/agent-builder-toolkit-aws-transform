"""Search tools using BM25 keyword search."""

import json

from rank_bm25 import BM25Okapi

from ...knowledge._lite import DATA_DIR, SOURCE_NAMES, get_documents

# Maximum characters to return per search result
MAX_CONTENT_LENGTH = 500


def keyword_search(query: str, top_k: int = 5) -> str:
    """Search ATX documentation using keyword search."""
    documents = get_documents()

    tokenized_docs = [doc[0].lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized_docs)
    scores = bm25.get_scores(query.lower().split())
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    output = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        doc, meta = documents[idx]
        output.append(
            {
                "content": doc[:MAX_CONTENT_LENGTH],
                "score": round(float(scores[idx]), 3),
                "source": meta.get("source", "unknown"),
                "citation": f"[{meta.get('source', 'unknown')}:{meta.get('name', meta.get('operation', 'doc'))}]",
            }
        )
    return json.dumps(output, indent=2)


def search_by_source(query: str, source: str, top_k: int = 5) -> str:
    """Search filtered by source."""
    documents = get_documents()

    # Filter documents by source
    source_name = SOURCE_NAMES.get(source, source)
    filtered = [
        (i, doc, meta)
        for i, (doc, meta) in enumerate(documents)
        if meta.get("source") == source_name
    ]

    if not filtered:
        return json.dumps([])

    tokenized_docs = [doc.lower().split() for _, doc, _ in filtered]
    bm25 = BM25Okapi(tokenized_docs)
    scores = bm25.get_scores(query.lower().split())
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    output = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        _, doc, meta = filtered[idx]
        output.append(
            {
                "content": doc[:MAX_CONTENT_LENGTH],
                "score": round(float(scores[idx]), 3),
                "source": meta.get("source", "unknown"),
                "citation": f"[{meta.get('source', 'unknown')}:{meta.get('name', meta.get('operation', 'doc'))}]",
            }
        )
    return json.dumps(output, indent=2)


def get_hitl_generation_prompt() -> str:
    """Get the complete HITL UI generation rules. Call this before generating domTreeJson."""
    return (DATA_DIR / "hitl_generation_rules.md").read_text()
