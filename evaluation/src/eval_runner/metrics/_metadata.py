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


def coerce_positive_number(value: object) -> float | None:
    """Coerce a metadata budget value into a positive float, or None.

    Budgets like ``max_latency_ms`` / ``max_tokens`` come from free-form YAML
    metadata, where a value can easily be authored as a quoted string ("1000").
    Returns the number when ``value`` is a positive int/float or a numeric
    string; returns None for anything else (missing, non-numeric, <= 0). Callers
    treat None as "no budget set" and abstain, so a typo'd budget reads as
    opt-out rather than a silent metric exception scored as a failure.
    """
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            n = float(value.strip())
        except ValueError:
            return None
        return n if n > 0 else None
    return None
