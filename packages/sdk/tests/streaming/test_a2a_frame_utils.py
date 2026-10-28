# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for raw A2A frame utilities."""

from agent_builder_sdk.streaming.a2a_frame_utils import (
    RAW_EXT_URI,
    extract_raw_event,
    frame_kind,
    frame_state,
    is_end_of_turn,
    is_final,
    is_terminal_state,
)


def _working_frame(event):
    return {
        "kind": "status-update",
        "taskId": "t-1",
        "contextId": "c-1",
        "final": False,
        "status": {
            "state": "working",
            "message": {
                "kind": "message",
                "parts": [{"kind": "data", "data": {RAW_EXT_URI: event}}],
            },
        },
    }


def test_frame_kind_and_state():
    frame = _working_frame({"data": "hi"})
    assert frame_kind(frame) == "status-update"
    assert frame_state(frame) == "working"
    assert frame_kind({}) is None
    assert frame_state({}) is None
    assert frame_state({"status": "not-a-dict"}) is None


def test_is_final():
    assert is_final({"final": True}) is True
    assert is_final({"final": False}) is False
    assert is_final({}) is False


def test_is_terminal_state():
    assert is_terminal_state("completed") is True
    assert is_terminal_state("failed") is True
    assert is_terminal_state("working") is False
    assert is_terminal_state("submitted") is False
    assert is_terminal_state(None) is False


def test_is_end_of_turn():
    assert is_end_of_turn({"final": True}) is True
    assert is_end_of_turn({"status": {"state": "completed"}}) is True
    assert is_end_of_turn({"status": {"state": "failed"}}) is True
    assert is_end_of_turn(_working_frame({"data": "x"})) is False


def test_extract_raw_event_roundtrip():
    event = {"data": "hello", "delta": {"foo": 1}}
    frame = _working_frame(event)
    assert extract_raw_event(frame) == event


def test_extract_raw_event_missing():
    # No status / no message / no data part → None.
    assert extract_raw_event({}) is None
    assert extract_raw_event({"status": {"state": "completed"}}) is None
    assert (
        extract_raw_event({"status": {"message": {"parts": [{"kind": "text", "text": "x"}]}}})
        is None
    )
    # data part present but wrong key.
    assert (
        extract_raw_event(
            {"status": {"message": {"parts": [{"kind": "data", "data": {"other": 1}}]}}}
        )
        is None
    )
