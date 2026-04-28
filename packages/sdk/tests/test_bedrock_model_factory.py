"""Tests for BedrockModelFactory."""

import os
from unittest.mock import Mock, patch

from agent_builder_sdk.bedrock_model_factory import BedrockModelFactory
from agent_builder_sdk.env_var import ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN


@patch.dict(os.environ, {}, clear=True)
@patch("agent_builder_sdk.bedrock_model_factory.BedrockModel")
def test_create_with_default_credentials(mock_bedrock_model):
    """Test BedrockModel creation with default credentials when no role ARN is set."""
    mock_model = Mock()
    mock_bedrock_model.return_value = mock_model

    result = BedrockModelFactory.create_with_shared_capacity_role(
        model_id="test-model", region_name="us-west-2"
    )

    mock_bedrock_model.assert_called_once_with(model_id="test-model", region_name="us-west-2")
    assert result == mock_model


@patch.dict(
    os.environ,
    {
        ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN: "arn:aws:iam::123456789012:role/BedrockSharedCapacityRole"
    },
)
@patch("agent_builder_sdk.bedrock_model_factory.RefreshableSession")
@patch("agent_builder_sdk.bedrock_model_factory.BedrockModel")
def test_create_with_shared_capacity_role(mock_bedrock_model, mock_refreshable_session):
    """Test BedrockModel creation with shared capacity role."""
    mock_session_obj = Mock()
    mock_boto_session = Mock()
    mock_session_obj.refreshable_session.return_value = mock_boto_session
    mock_refreshable_session.return_value = mock_session_obj

    mock_model = Mock()
    mock_bedrock_model.return_value = mock_model

    result = BedrockModelFactory.create_with_shared_capacity_role(
        model_id="test-model", region_name="us-west-2"
    )

    mock_refreshable_session.assert_called_once_with(
        role_arn="arn:aws:iam::123456789012:role/BedrockSharedCapacityRole",
        session_name="platform-base-agent",
        region_name="us-west-2",
    )
    mock_bedrock_model.assert_called_once_with(
        model_id="test-model", boto_session=mock_boto_session
    )
    assert result == mock_model


@patch.dict(
    os.environ,
    {
        ENV_KEY_BEDROCK_SHARED_CAPACITY_ROLE_ARN: "arn:aws:iam::123456789012:role/BedrockSharedCapacityRole"
    },
)
@patch("agent_builder_sdk.bedrock_model_factory.RefreshableSession")
@patch("agent_builder_sdk.bedrock_model_factory.BedrockModel")
def test_create_handles_exceptions(mock_bedrock_model, mock_refreshable_session):
    """Test BedrockModel creation handles exceptions gracefully."""
    mock_refreshable_session.side_effect = Exception("Role assumption failed")

    mock_model = Mock()
    mock_bedrock_model.return_value = mock_model

    result = BedrockModelFactory.create_with_shared_capacity_role(
        model_id="test-model", region_name="us-west-2"
    )

    mock_bedrock_model.assert_called_once_with(model_id="test-model", region_name="us-west-2")
    assert result == mock_model
