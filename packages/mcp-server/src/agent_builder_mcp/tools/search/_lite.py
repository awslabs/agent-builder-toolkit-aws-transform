# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Search tools using BM25 keyword search."""

import functools
import json
import re

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

_WORD_START = re.compile(r"(?<!\S)\S")


@functools.cache
def _words(text: str) -> frozenset[str]:
    """The stemmed words of a text that an excerpt can show.

    Cached, because stemming is the slow part of a search. These texts are cut from the chunks at
    fixed places, not by the query, so the cache cannot outgrow the knowledge base.
    """
    return frozenset(tokenize(text))


def _excerpt(doc: str, query_tokens: list[str]) -> str:
    """The MAX_CONTENT_LENGTH characters of a chunk that show the most query words.

    A chunk can hold several FAQ answers; cutting it from the start would show the first answer,
    not the one that matched (e.g. the A2UI answer sits 1255 characters into its chunk). The excerpt
    starts at the chunk start or at a heading; in a chunk without headings (SDK and API docs) also
    at the first word of every half excerpt.
    """
    # A short document keeps its newlines, so a heading starts a line; a chunked document is one line.
    # "# " is not taken as a heading: in many chunks it is a code comment.
    heading = r"(?m)^#{2,6} " if "\n" in doc else r"(?<!\S)#{2,6} "
    headings = [m.start() for m in re.finditer(heading, doc) if m.start() > 0]
    starts = [0] + headings
    if not headings and len(doc) > MAX_CONTENT_LENGTH:
        half = MAX_CONTENT_LENGTH // 2
        starts += [m.start() for at in range(half, len(doc), half) if (m := _WORD_START.search(doc, at))]
    wanted = set(query_tokens)

    def hits(start: int) -> tuple[int, int]:
        """Query words in the text that is returned, then in the part of it before the next heading."""
        shown = doc[start : start + MAX_CONTENT_LENGTH]
        cut = next((h for h in headings if h > start), len(doc)) - start
        own, rest = wanted & _words(shown[:cut]), wanted & _words(shown[cut:])
        return len(own | rest), len(own)

    # The second count keeps a short section from winning on the words of the section after it.
    best = max(starts, key=lambda start: (*hits(start), -start))
    return doc[best : best + MAX_CONTENT_LENGTH]


def keyword_search(query: str, top_k: int = 5) -> str:
    """Search ATX documentation using keyword search."""
    documents = get_documents()
    bm25 = get_bm25()

    query_tokens = tokenize(query)
    # Only expand natural-language queries (multi-word), not code identifiers.
    # Single identifiers like "CreateHitlTask" get CamelCase-split by tokenize()
    # and expansion would add noise tokens that outrank the exact match.
    # Synonyms are for the ranking only: BM25 weights them down, the word count in _excerpt would not.
    ranking_tokens = expand_query(query_tokens) if " " in query.strip() else query_tokens
    scores = bm25.get_scores(ranking_tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    output = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        doc, meta = documents[idx]
        result: dict[str, object] = {
            "content": _excerpt(doc, query_tokens),
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
            "content": _excerpt(doc, query_tokens),
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
