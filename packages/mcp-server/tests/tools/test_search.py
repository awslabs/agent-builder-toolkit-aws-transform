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
