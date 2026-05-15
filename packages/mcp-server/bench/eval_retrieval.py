# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Retrieval quality evaluation engine for BM25 search.

Loads a golden dataset (JSONL), executes searches against the BM25 index,
computes Recall@K, MRR, Precision@K, and Sufficiency@K metrics, and
produces structured reports.

Scoring notes:
- Adversarial queries (category="adversarial") are excluded from overall
  Recall/MRR/Precision. They test graceful degradation under typos and
  nonsense input — BM25 cannot do character-level fuzzy matching — so
  including them would penalize a correct system.
- Some golden queries use legacy shorthand in query text. This is intentional:
  real users type abbreviations even though the canonical source names differ.
  Retrieval succeeds on co-occurring terms like "register" or "deploy".

Usage:
    python3 bench/eval_retrieval.py [--golden PATH] [--top-k N] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_builder_mcp.knowledge._lite import setup_kb
from agent_builder_mcp.tools.search._lite import keyword_search, search_by_source

# ---------------------------------------------------------------------------
# Golden dataset loader and matching helpers
# ---------------------------------------------------------------------------


def load_golden(path: str | Path) -> list[dict]:
    """Load golden dataset from a JSONL file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Golden dataset not found: {path}")
    entries: list[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _is_relevant_match(result: dict, expected: dict) -> bool:
    """Check if a search result matches an expected relevant document."""
    if result.get("source") != expected.get("source"):
        return False
    name = expected.get("name")
    if name is None:
        return True
    name_lower = name.lower()
    citation = result.get("citation", "").lower()
    content = result.get("content", "").lower()
    return name_lower in citation or name_lower in content


def _execute_query(entry: dict, top_k: int) -> list[dict]:
    """Dispatch to keyword_search or search_by_source based on entry['tool']."""
    tool = entry["tool"]
    tool_args = entry.get("tool_args", {})
    query = tool_args["query"]
    effective_top_k = tool_args.get("top_k", top_k)

    if tool == "keyword_search":
        raw = keyword_search(query, effective_top_k)
    elif tool == "search_by_source":
        source = tool_args["source"]
        raw = search_by_source(query, source, effective_top_k)
    else:
        raise ValueError(f"Unknown tool: {tool}")

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Metric computation functions
# ---------------------------------------------------------------------------


def _compute_recall(results: list[dict], relevant: list[dict]) -> float:
    """Recall@K = |relevant found in results| / |relevant expected|."""
    if not relevant:
        return 0.0
    found = sum(
        1
        for exp in relevant
        if any(_is_relevant_match(r, exp) for r in results)
    )
    return found / len(relevant)


def _compute_mrr(results: list[dict], relevant: list[dict]) -> float:
    """MRR = 1/rank of first relevant result (1-indexed), or 0.0 if none."""
    for rank, result in enumerate(results, start=1):
        if any(_is_relevant_match(result, exp) for exp in relevant):
            return 1.0 / rank
    return 0.0


def _compute_precision(results: list[dict], relevant: list[dict], k: int) -> float:
    """Precision@K = |relevant in top-K| / K."""
    if k == 0:
        return 0.0
    top_k_results = results[:k]
    relevant_count = sum(
        1
        for r in top_k_results
        if any(_is_relevant_match(r, exp) for exp in relevant)
    )
    return relevant_count / k


def _compute_sufficiency(results: list[dict], sufficient_info: list[str]) -> float:
    """Sufficiency@K = |info strings found in concatenated content| / |info strings|."""
    if not sufficient_info:
        return 0.0
    combined_content = " ".join(r.get("content", "") for r in results).lower()
    found = sum(
        1
        for info in sufficient_info
        if info.lower() in combined_content
    )
    return found / len(sufficient_info)


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------


def evaluate(golden: list[dict], top_k: int = 5) -> dict:
    """Run evaluation against the BM25 search index."""
    setup_kb()

    per_query: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for entry in golden:
        query_str = entry.get("query", "")
        category = entry.get("category", "unknown")
        relevant = entry.get("relevant", [])
        sufficient_info = entry.get("sufficient_info", [])

        try:
            results = _execute_query(entry, top_k)

            recall = _compute_recall(results, relevant)
            mrr = _compute_mrr(results, relevant)
            precision = _compute_precision(results, relevant, top_k)
            sufficiency = _compute_sufficiency(results, sufficient_info)

            matched: list[str] = []
            for exp in relevant:
                if any(_is_relevant_match(r, exp) for r in results):
                    source = exp.get("source", "")
                    name = exp.get("name", "")
                    if name:
                        matched.append(f"{source}:{name}")
                    else:
                        matched.append(source)

            per_query.append({
                "query": query_str,
                "category": category,
                "recall": recall,
                "mrr": mrr,
                "precision": precision,
                "sufficiency": sufficiency,
                "matched": matched,
                "results": results,
                "expected": relevant,
            })

            if recall == 0.0:
                got_top3 = [r.get("source", "") for r in results[:3]]
                failures.append({
                    "query": query_str,
                    "category": category,
                    "expected": [
                        f"{exp.get('source', '')}:{exp.get('name', '')}"
                        if exp.get("name")
                        else exp.get("source", "")
                        for exp in relevant
                    ],
                    "got_top3": got_top3,
                })

        except Exception as exc:
            per_query.append({
                "query": query_str,
                "category": category,
                "recall": 0.0,
                "mrr": 0.0,
                "precision": 0.0,
                "sufficiency": 0.0,
                "matched": [],
                "results": [],
                "expected": relevant,
            })
            failures.append({
                "query": query_str,
                "category": category,
                "expected": [
                    f"{exp.get('source', '')}:{exp.get('name', '')}"
                    if exp.get("name")
                    else exp.get("source", "")
                    for exp in relevant
                ],
                "got_top3": [],
                "error": str(exc),
            })

    # --- Aggregate overall metrics ---
    # Exclude adversarial queries from overall recall/MRR — they test graceful
    # degradation under typos and nonsense input, not retrieval quality.
    scored_queries = [
        pq for pq in per_query if pq["category"] != "adversarial"
    ]
    total = len(per_query)
    scored_total = len(scored_queries)
    if scored_total > 0:
        overall_recall = sum(pq["recall"] for pq in scored_queries) / scored_total
        overall_mrr = sum(pq["mrr"] for pq in scored_queries) / scored_total
        overall_precision = sum(pq["precision"] for pq in scored_queries) / scored_total
    else:
        overall_recall = 0.0
        overall_mrr = 0.0
        overall_precision = 0.0

    suff_entries = [
        (pq, entry)
        for pq, entry in zip(per_query, golden)
        if entry.get("sufficient_info")
    ]
    if suff_entries:
        overall_sufficiency = sum(pq["sufficiency"] for pq, _ in suff_entries) / len(suff_entries)
    else:
        overall_sufficiency = 0.0

    overall = {
        "recall": overall_recall,
        "mrr": overall_mrr,
        "precision": overall_precision,
        "sufficiency": overall_sufficiency,
        "sufficiency_count": len(suff_entries),
        "scored_queries": scored_total,
    }

    # --- Aggregate per-category metrics ---
    categories: dict[str, list[dict]] = {}
    category_golden: dict[str, list[dict]] = {}
    for pq, entry in zip(per_query, golden):
        cat = pq["category"]
        categories.setdefault(cat, []).append(pq)
        category_golden.setdefault(cat, []).append(entry)

    per_category: dict[str, dict[str, float]] = {}
    for cat, pqs in categories.items():
        n = len(pqs)
        cat_recall = sum(pq["recall"] for pq in pqs) / n
        cat_mrr = sum(pq["mrr"] for pq in pqs) / n
        cat_precision = sum(pq["precision"] for pq in pqs) / n

        cat_suff_entries = [
            pq
            for pq, entry in zip(pqs, category_golden[cat])
            if entry.get("sufficient_info")
        ]
        if cat_suff_entries:
            cat_sufficiency = sum(pq["sufficiency"] for pq in cat_suff_entries) / len(cat_suff_entries)
        else:
            cat_sufficiency = 0.0

        per_category[cat] = {
            "recall": cat_recall,
            "mrr": cat_mrr,
            "precision": cat_precision,
            "sufficiency": cat_sufficiency,
            "count": n,
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "top_k": top_k,
        "total_queries": total,
        "overall": overall,
        "per_category": per_category,
        "per_query": per_query,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Report formatting and CLI entry point
# ---------------------------------------------------------------------------


def format_report(results: dict) -> str:
    """Format evaluation results as a human-readable text report."""
    top_k = results.get("top_k", 5)
    total = results.get("total_queries", 0)
    overall = results.get("overall", {})
    per_category = results.get("per_category", {})
    failures = results.get("failures", [])

    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"RETRIEVAL EVALUATION REPORT ({total} queries, top_k={top_k})")
    lines.append(sep)

    scored = overall.get("scored_queries", total)
    lines.append(f"Overall (excludes adversarial, n={scored}):")
    lines.append(f"  Recall@{top_k}:      {overall.get('recall', 0.0):.3f}")
    lines.append(f"  MRR:           {overall.get('mrr', 0.0):.3f}")
    lines.append(f"  Precision@{top_k}:   {overall.get('precision', 0.0):.3f}")

    suff_count = overall.get("sufficiency_count", total)
    lines.append(
        f"  Sufficiency@{top_k}: {overall.get('sufficiency', 0.0):.3f}"
        f"  ({suff_count}/{total} queries evaluated)"
    )

    lines.append("")
    lines.append("By category:")
    for cat_name in sorted(per_category.keys()):
        cat = per_category[cat_name]
        count = cat.get("count", 0)
        lines.append(
            f"  {cat_name} ({count}):"
            f"   Recall={cat.get('recall', 0.0):.3f}"
            f"  MRR={cat.get('mrr', 0.0):.3f}"
            f"  Prec={cat.get('precision', 0.0):.3f}"
            f"  Suff={cat.get('sufficiency', 0.0):.3f}"
        )

    if failures:
        lines.append("")
        lines.append(f"Failures (queries with Recall@{top_k} = 0):")
        for f in failures:
            query = f.get("query", "?")
            category = f.get("category", "?")
            expected = f.get("expected", [])
            got_top3 = f.get("got_top3", [])
            error = f.get("error")

            if error:
                lines.append(f'  [{category}] "{query}" — error: {error}')
            else:
                expected_str = ", ".join(expected)
                got_str = ", ".join(got_top3) if got_top3 else "[]"
                lines.append(
                    f'  [{category}] "{query}" — expected: {expected_str}, got: [{got_str}]'
                )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    default_golden = str(Path(__file__).parent / "golden_queries.jsonl")

    parser = argparse.ArgumentParser(
        description="Evaluate BM25 retrieval quality against a golden dataset."
    )
    parser.add_argument(
        "--golden",
        default=default_golden,
        help="Path to golden JSONL file (default: bench/golden_queries.jsonl)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results per query (default: 5)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write raw JSON results (optional)",
    )

    args = parser.parse_args()

    golden = load_golden(args.golden)
    results = evaluate(golden, top_k=args.top_k)

    report = format_report(results)
    print(report)

    if args.output:
        output_results = dict(results)
        output_results["per_query"] = [
            {k: v for k, v in pq.items() if k != "results"}
            for pq in results["per_query"]
        ]
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_results, f, indent=2, default=str)
        print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
