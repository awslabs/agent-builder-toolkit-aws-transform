# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for StreamingConfig defaults."""

from agent_builder_sdk.streaming import DEFAULT_STREAMING_CONFIG, StreamingConfig


def test_defaults_all_on():
    cfg = StreamingConfig()
    assert cfg.emit_reasoning is True
    assert cfg.emit_tool_calls is True
    assert cfg.agent_idle_ttl_seconds == 30 * 60


def test_default_singleton_all_on():
    assert DEFAULT_STREAMING_CONFIG == StreamingConfig()


def test_opt_out_single_category():
    cfg = StreamingConfig(emit_reasoning=False)
    assert cfg.emit_reasoning is False
    assert cfg.emit_tool_calls is True


def test_idle_ttl_configurable():
    cfg = StreamingConfig(agent_idle_ttl_seconds=120)
    assert cfg.agent_idle_ttl_seconds == 120


def test_frozen():
    import dataclasses

    import pytest

    cfg = StreamingConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.emit_reasoning = False  # type: ignore[misc]
