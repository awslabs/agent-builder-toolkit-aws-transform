"""Tests for knowledge base setup and search."""

import json

import pytest


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset module-level globals so each test starts fresh."""
    from agent_builder_mcp.knowledge import _lite

    _lite._documents = None
    yield
    _lite._documents = None


class TestChunkText:
    """Tests for text chunking."""

    def test_chunk_text_splits(self) -> None:
        from agent_builder_mcp.knowledge._lite import _chunk_text

        text = " ".join(f"word{i}" for i in range(100))
        chunks = _chunk_text(text, chunk_size=30)
        assert len(chunks) == 4

    def test_chunk_text_single_chunk(self) -> None:
        from agent_builder_mcp.knowledge._lite import _chunk_text

        chunks = _chunk_text("hello world", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_chunk_text_empty(self) -> None:
        from agent_builder_mcp.knowledge._lite import _chunk_text

        chunks = _chunk_text("", chunk_size=512)
        assert chunks == []


class TestLoadDocuments:
    """Tests for loading raw data files into document tuples."""

    def test_loads_documents(self) -> None:
        from agent_builder_mcp.knowledge._lite import _load_documents_from_data

        docs = _load_documents_from_data()
        assert len(docs) > 0

    def test_documents_are_tuples(self) -> None:
        from agent_builder_mcp.knowledge._lite import _load_documents_from_data

        docs = _load_documents_from_data()
        for text, meta in docs:
            assert isinstance(text, str)
            assert isinstance(meta, dict)
            assert "source" in meta

    def test_all_sources_loaded(self) -> None:
        from agent_builder_mcp.knowledge._lite import (
            SOURCE_NAMES,
            _load_documents_from_data,
        )

        docs = _load_documents_from_data()
        loaded_sources = {meta["source"] for _, meta in docs}
        for source_name in SOURCE_NAMES.values():
            assert source_name in loaded_sources, f"Source {source_name} not loaded"


class TestSetupKb:
    """Tests for knowledge base initialization."""

    def test_setup_loads_documents(self) -> None:
        from agent_builder_mcp.knowledge._lite import get_documents, setup_kb

        setup_kb()
        docs = get_documents()
        assert len(docs) > 0

    def test_setup_is_idempotent(self) -> None:
        from agent_builder_mcp.knowledge._lite import get_documents, setup_kb

        setup_kb()
        docs1 = get_documents()
        setup_kb()
        docs2 = get_documents()
        assert docs1 is docs2  # same object, not reloaded


class TestKnowledgeBase:
    """Tests for knowledge base router."""

    def test_lite_mode_default(self) -> None:
        from agent_builder_mcp import knowledge

        assert knowledge.LITE_MODE is True


class TestKeywordSearch:
    """Tests for BM25 search."""

    def test_returns_results(self) -> None:
        from agent_builder_mcp.tools.search._lite import keyword_search

        result = keyword_search("how to register an agent", top_k=3)
        parsed = json.loads(result)
        assert len(parsed) > 0

    def test_result_structure(self) -> None:
        from agent_builder_mcp.tools.search._lite import keyword_search

        result = keyword_search("deploy agent", top_k=2)
        parsed = json.loads(result)
        for item in parsed:
            assert "content" in item
            assert "score" in item
            assert "source" in item
            assert "citation" in item

    def test_skips_zero_score_results(self) -> None:
        from agent_builder_mcp.tools.search._lite import keyword_search

        result = keyword_search("xyznonexistentterm123", top_k=5)
        parsed = json.loads(result)
        for item in parsed:
            assert item["score"] > 0


class TestSearchBySource:
    """Tests for source-filtered search."""

    def test_filters_by_source(self) -> None:
        from agent_builder_mcp.tools.search._lite import search_by_source

        result = search_by_source("create session", source="agentic-api", top_k=3)
        parsed = json.loads(result)
        for item in parsed:
            assert item["source"] == "ElasticGumbyAgenticApiModel"

    def test_unknown_source_returns_empty(self) -> None:
        from agent_builder_mcp.tools.search._lite import search_by_source

        result = search_by_source("test", source="nonexistent-source", top_k=3)
        parsed = json.loads(result)
        assert parsed == []
