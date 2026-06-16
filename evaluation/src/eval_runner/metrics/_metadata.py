# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for reading metric config off a test case's ``metadata``."""

from __future__ import annotations


def coerce_str_list(value: object) -> list[str]:
    """Coerce a metadata value into a list of non-empty, stripped strings.

    Accepts a list/tuple of strings or a single string; anything else (or None)
    yields an empty list. Non-string elements are *dropped*, not stringified —
    so a stray ``null`` in ``["expected_tools": [null, "search"]]`` can't become
    a phantom tool named ``"None"`` that silently never matches. Used by the
    generic metrics to read their per-test config (expected tools, completion/
    error markers) from the free-form ``TestCase.metadata`` dict.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [s for v in value if isinstance(v, str) and (s := v.strip())]
