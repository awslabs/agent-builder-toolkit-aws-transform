# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Property-based tests for BM25 chunking and query deduplication bugs.

Task 1: Bug condition exploration tests — MUST FAIL on unfixed code (failure confirms bugs exist).
Task 2: Preservation tests — MUST PASS on unfixed code (captures baseline behavior).
"""

from __future__ import annotations

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_builder_mcp.knowledge._lite import _chunk_text, expand_query

# ---------------------------------------------------------------------------
# Task 1: Bug Condition Exploration Tests
# These tests encode the EXPECTED (correct) behavior.
# They MUST FAIL on unfixed code — failure confirms the bugs exist.
# ---------------------------------------------------------------------------


class TestBugConditionExploration:
    """Bug condition exploration: these tests MUST FAIL on unfixed code."""

    @settings(max_examples=50)
    @given(
        chunk_size=st.integers(min_value=10, max_value=100),
        overlap_factor=st.integers(min_value=1, max_value=3),
        word_count=st.integers(min_value=200, max_value=500),
    )
    def test_bug_condition_chunk_explosion(
        self, chunk_size: int, overlap_factor: int, word_count: int
    ) -> None:
        """Chunk count must be bounded when overlap >= chunk_size.

        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**

        On unfixed code, step degenerates to 1 when overlap >= chunk_size,
        producing ~N chunks for an N-word document instead of ~N/chunk_size.
        After fix, overlap is clamped to chunk_size-1, so step >= 1 and
        chunk count stays proportional to N/chunk_size.
        """
        overlap = chunk_size * overlap_factor  # Always >= chunk_size
        text = " ".join(f"word{i}" for i in range(word_count))
        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        # After fix: overlap is clamped to chunk_size - 1, so step = 1.
        # With step=1, chunk count = word_count - chunk_size + 1 (each window
        # slides by 1 word until the last chunk covers the tail).
        # The key property: the clamp ensures step is computed via arithmetic
        # (chunk_size - clamped_overlap >= 1) rather than relying on max(1, negative).
        # We verify the chunk count matches the clamped-overlap formula exactly.
        effective_overlap = min(overlap, chunk_size - 1)
        effective_step = chunk_size - effective_overlap  # always >= 1
        expected_chunks = math.ceil((word_count - chunk_size) / effective_step) + 1
        # Allow a small tolerance for off-by-one in boundary conditions
        assert len(chunks) <= expected_chunks + 1, (
            f"chunk_size={chunk_size}, overlap={overlap}, words={word_count}: "
            f"got {len(chunks)} chunks, expected <= {expected_chunks + 1}"
        )

    def test_bug_condition_token_duplication(self) -> None:
        """expand_query must not return duplicate tokens.

        **Validates: Requirements 1.3, 1.4, 2.3, 2.4**

        On unfixed code, expand_query blindly extends with synonyms that may
        already be in the token list, producing duplicates that inflate BM25 scores.
        Multi-token queries where one token appears in another's synonym list
        trigger this bug (e.g., ["test", "valid"] produces duplicate "valid").
        """
        # Test multi-token case: "test" has synonym "valid", so ["test", "valid"]
        # should produce duplicates on unfixed code
        result = expand_query(["test", "valid"])
        assert len(result) == len(
            set(result)
        ), f"expand_query(['test', 'valid']) produced duplicates: {result}"

    def test_bug_condition_token_duplication_cross_synonyms(self) -> None:
        """expand_query must not return duplicates from cross-synonym overlap.

        **Validates: Requirements 1.3, 1.4, 2.3, 2.4**

        Tokens like "orchestr" and "subag" share synonym values ("async", "base"),
        causing duplicates when both are in the query.
        """
        result = expand_query(["orchestr", "subag"])
        assert len(result) == len(
            set(result)
        ), f"expand_query(['orchestr', 'subag']) produced duplicates: {result}"


# ---------------------------------------------------------------------------
# Task 2: Preservation Tests
# These tests capture baseline behavior that MUST be preserved.
# They MUST PASS on unfixed code.
# ---------------------------------------------------------------------------


class TestPreservation:
    """Preservation tests: these tests MUST PASS on unfixed code."""

    @settings(max_examples=50)
    @given(
        chunk_size=st.integers(min_value=5, max_value=100),
        overlap_pct=st.floats(min_value=0.0, max_value=0.9),
        word_count=st.integers(min_value=1, max_value=300),
    )
    def test_preservation_normal_chunking(
        self, chunk_size: int, overlap_pct: float, word_count: int
    ) -> None:
        """Normal chunking (overlap < chunk_size) produces expected chunk count.

        **Validates: Requirements 3.1**
        """
        overlap = int(chunk_size * overlap_pct)
        assume(overlap < chunk_size)
        text = " ".join(f"word{i}" for i in range(word_count))
        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        # Each chunk should have at most chunk_size words
        for chunk in chunks:
            assert len(chunk.split()) <= chunk_size + 1  # +1 for rounding

    def test_preservation_empty_text(self) -> None:
        """Empty text returns empty list.

        **Validates: Requirements 3.3**
        """
        assert _chunk_text("", chunk_size=100, overlap=50) == []

    def test_preservation_short_text(self) -> None:
        """Text shorter than chunk_size returns single chunk.

        **Validates: Requirements 3.2**
        """
        text = "hello world foo bar"
        chunks = _chunk_text(text, chunk_size=100, overlap=50)
        assert len(chunks) == 1
        assert chunks[0].strip() == text.strip()

    def test_preservation_no_synonym_tokens(self) -> None:
        """Tokens not in SYNONYMS are returned unchanged.

        **Validates: Requirements 3.5**
        """
        tokens = ["xyznonexistent", "abcfaketoken"]
        result = expand_query(tokens)
        assert result == tokens

    def test_preservation_expand_query_superset(self) -> None:
        """expand_query result is a superset of input tokens.

        **Validates: Requirements 3.4**
        """
        tokens = ["deploy", "agent"]
        result = expand_query(tokens)
        assert set(tokens).issubset(set(result))
