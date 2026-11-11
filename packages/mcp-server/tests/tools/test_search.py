# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for search tools (BM25 keyword search)."""

import json

from agent_builder_mcp.tools.search import _lite


class TestKeywordSearch:
    """Tests for keyword_search function."""

    def test_keyword_search_returns_results(self) -> None:
        """Test that search returns results."""
        result = _lite.keyword_search("register agent", top_k=3)
        parsed = json.loads(result)
        assert len(parsed) >= 1
        assert "content" in parsed[0]
        assert "citation" in parsed[0]


class TestSearchBySource:
    """Tests for search_by_source function."""

    def test_search_by_source_filters(self) -> None:
        """Test that search filters by source."""
        result = _lite.search_by_source("requestContext", source="agentic-api", top_k=3)
        parsed = json.loads(result)
        assert len(parsed) >= 1
        for item in parsed:
            assert item["source"] == "TransformAgenticApiModel"


class TestExcerpt:
    """The excerpt starts at the section of the chunk that matches the query."""

    def test_excerpt_starts_at_the_matching_heading(self) -> None:
        doc = "### How do I deploy? " + "Use the pipeline. " * 60 + "### How can my agent show tables? Use A2UI."
        out = _lite._excerpt(doc, _lite.tokenize("agent show tables"))
        assert out.startswith("### How can my agent show tables?")

    def test_excerpt_without_a_match_starts_at_the_beginning(self) -> None:
        doc = "### First. text ### Second. text"
        assert _lite._excerpt(doc, ["zzz"]).startswith("### First.")

    def test_a2ui_faq_is_in_the_top_results(self) -> None:
        parsed = json.loads(_lite.keyword_search("how can my agent show a table, a form or a chart in chat", top_k=5))
        assert any("How can my agent show tables" in r["content"] for r in parsed)
