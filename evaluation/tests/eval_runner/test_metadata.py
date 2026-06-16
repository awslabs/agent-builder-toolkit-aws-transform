# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared metric-metadata helper (coerce_str_list)."""

from eval_runner.metrics._metadata import coerce_str_list


class TestCoerceStrList:
    def test_none_yields_empty(self):
        assert coerce_str_list(None) == []

    def test_non_collection_yields_empty(self):
        # A non-str, non-list/tuple value disables the metric (returns []) rather
        # than crashing — e.g. a misconfigured int/dict in metadata.
        assert coerce_str_list(42) == []
        assert coerce_str_list({"a": 1}) == []

    def test_single_string_is_wrapped(self):
        assert coerce_str_list("keyword_search") == ["keyword_search"]

    def test_list_is_stripped_and_blank_filtered(self):
        assert coerce_str_list(["a", "  ", "", " b "]) == ["a", "b"]

    def test_tuple_accepted(self):
        assert coerce_str_list(("a", "b")) == ["a", "b"]

    def test_non_string_elements_dropped_not_stringified(self):
        # The bug this guards: a stray null/int must NOT become a phantom entry
        # like "None"/"7" that can never match a real tool/marker.
        assert coerce_str_list([None, "search", 7, "deploy"]) == ["search", "deploy"]

    def test_blank_only_string_yields_empty(self):
        assert coerce_str_list("   ") == []
