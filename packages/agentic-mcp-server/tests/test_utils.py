# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the utils module.
"""

from agent_builder_agentic_mcp.utils import dig


def test_dig_success():
    """Test successful nested dictionary access."""
    # Arrange
    test_dict = {"level1": {"level2": {"level3": "target_value"}}}

    # Act
    result = dig(test_dict, ["level1", "level2", "level3"])

    # Assert
    assert result == "target_value"


def test_dig_missing_key():
    """Test dig with missing key returns default."""
    # Arrange
    test_dict = {"level1": {"level2": "value"}}

    # Act
    result = dig(test_dict, ["level1", "missing_key"], default="default_value")

    # Assert
    assert result == "default_value"


def test_dig_none_default():
    """Test dig with missing key returns None by default."""
    # Arrange
    test_dict = {"level1": {"level2": "value"}}

    # Act
    result = dig(test_dict, ["level1", "missing_key"])

    # Assert
    assert result is None


def test_dig_non_dict_value():
    """Test dig when encountering non-dict value."""
    # Arrange
    test_dict = {"level1": "string_value"}

    # Act
    result = dig(test_dict, ["level1", "level2"])

    # Assert
    assert result == "string_value"


def test_dig_none_input():
    """Test dig with None input."""
    # Act
    result = dig(None, ["key"], default="default")

    # Assert
    assert result is None  # The function returns None when input is None


def test_dig_empty_keys():
    """Test dig with empty keys list."""
    # Arrange
    test_dict = {"key": "value"}

    # Act
    result = dig(test_dict, [])

    # Assert
    assert result == test_dict


def test_dig_single_level():
    """Test dig with single level access."""
    # Arrange
    test_dict = {"key": "value"}

    # Act
    result = dig(test_dict, ["key"])

    # Assert
    assert result == "value"


def test_dig_with_list_value():
    """Test dig when target value is a list."""
    # Arrange
    test_dict = {"level1": {"level2": ["item1", "item2", "item3"]}}

    # Act
    result = dig(test_dict, ["level1", "level2"])

    # Assert
    assert result == ["item1", "item2", "item3"]


def test_dig_with_numeric_keys():
    """Test dig with numeric keys (as strings)."""
    # Arrange
    test_dict = {"0": {"1": {"2": "numeric_path_value"}}}

    # Act
    result = dig(test_dict, ["0", "1", "2"])

    # Assert
    assert result == "numeric_path_value"


def test_dig_partial_path_exists():
    """Test dig when partial path exists but not complete."""
    # Arrange
    test_dict = {"level1": {"level2": "end_value"}}

    # Act
    result = dig(test_dict, ["level1", "level2", "level3"], default="not_found")

    # Assert
    assert result == "end_value"  # Returns the value at level2, not the default
