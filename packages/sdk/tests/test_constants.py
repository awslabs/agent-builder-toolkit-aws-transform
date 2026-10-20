# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared send-message timeout constants and validation."""

import logging

import pytest

from agent_builder_sdk.constants import (
    DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS,
    DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS,
    MAX_SEND_MESSAGE_TIMEOUT_SECONDS,
    validate_send_message_timeout,
)


def test_send_message_timeout_defaults():
    assert DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS == 28
    assert MAX_SEND_MESSAGE_TIMEOUT_SECONDS == 28
    assert DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS == 300


@pytest.mark.parametrize("timeout", [1, 20, MAX_SEND_MESSAGE_TIMEOUT_SECONDS])
def test_validate_send_message_timeout_accepts_up_to_max_without_warning(timeout, caplog):
    with caplog.at_level(logging.WARNING):
        assert validate_send_message_timeout(timeout) == timeout
    assert caplog.records == []


@pytest.mark.parametrize("timeout", [29, 60])
def test_validate_send_message_timeout_above_max_warns_and_keeps_value(timeout, caplog):
    """Existing agents with a longer timeout keep working: the value is kept, and a warning is logged."""
    with caplog.at_level(logging.WARNING):
        assert validate_send_message_timeout(timeout) == timeout
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert f"{timeout}s exceeds the maximum of 28s" in message
    assert "acknowledgment cut off" in message
