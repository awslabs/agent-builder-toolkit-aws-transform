# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the tool_use_prompts module."""

from unittest.mock import patch

from agent_builder_sdk import tool_use_prompts


def test_apply_tool_use_prompts_claude():
    """Test that apply_tool_use_prompts correctly applies Claude prompts."""
    # Arrange
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    prompt = "You are a helpful assistant."

    # Act
    result = tool_use_prompts.apply_tool_use_prompts(model_id, prompt)

    # Assert
    assert prompt in result
    assert tool_use_prompts.CLAUDE_PROMPT in result
    assert result == f"{prompt}\n\n{tool_use_prompts.CLAUDE_PROMPT}"


def test_apply_tool_use_prompts_claude_already_applied():
    """Test that apply_tool_use_prompts doesn't duplicate Claude prompts."""
    # Arrange
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    prompt = f"You are a helpful assistant.\n\n{tool_use_prompts.CLAUDE_PROMPT}"

    # Act
    result = tool_use_prompts.apply_tool_use_prompts(model_id, prompt)

    # Assert
    assert result == prompt  # Should be unchanged


def test_apply_tool_use_prompts_non_claude():
    """Test that apply_tool_use_prompts doesn't apply Claude prompts to non-Claude models."""
    # Arrange
    model_id = "amazon.titan-text-express-v1"
    prompt = "You are a helpful assistant."

    # Act
    result = tool_use_prompts.apply_tool_use_prompts(model_id, prompt)

    # Assert
    assert result == prompt  # Should be unchanged
    assert tool_use_prompts.CLAUDE_PROMPT not in result


@patch("agent_builder_sdk.tool_use_prompts.logger")
def test_apply_tool_use_prompts_logging(mock_logger):
    """Test that apply_tool_use_prompts logs correctly."""
    # Arrange
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    prompt = "You are a helpful assistant."

    # Act
    tool_use_prompts.apply_tool_use_prompts(model_id, prompt)

    # Assert
    mock_logger.info.assert_called_once_with(
        f"Applying Claude tool use prompts to {model_id}'s prompt"
    )
