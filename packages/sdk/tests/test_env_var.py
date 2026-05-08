# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.api_model import AgenticApiRequestContext
from agent_builder_sdk.env_var import (
    get_agent_context_from_env,
    get_agentic_api_request_context_with_current_token,
    get_bedrock_shared_capacity_role_arn,
    get_initial_agent_runtime_context_from_env,
    is_external_agentic_api_enabled,
    retrieve_auth_token,
    set_runtime_env_vars,
    should_use_prod_bedrock_capacity,
    validate_required_env_vars,
)
from agent_builder_sdk.server.server_models import AgentRuntimeContext


class TestGetAgentContextFromEnv:
    """Tests for get_agent_context_from_env function (moved from test_utils.py)"""

    def test_get_agent_context_from_env_success(self):
        """Test that get_agent_context_from_env successfully creates context from environment variables."""
        # Arrange
        env_vars = {
            "JOB_ID": "test-job-id",
            "WORKSPACE_ID": "test-workspace-id",
            "AGENT_INSTANCE_ID": "test-agent-instance-id",
            "AUTHORIZATION_TOKEN": "test-auth-token",
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            with mock.patch(
                "agent_builder_sdk.env_var.retrieve_auth_token", return_value="test-auth-token"
            ):
                # Act
                context = get_agent_context_from_env()

                # Assert
                assert isinstance(context, AgenticApiRequestContext)
                assert context.job_id == "test-job-id"
                assert context.workspace_id == "test-workspace-id"
                assert context.agent_instance_id == "test-agent-instance-id"
                assert context.authorization_token == "test-auth-token"

    def test_get_agent_context_from_env_missing_multiple_vars(self):
        """Test that get_agent_context_from_env raises ValueError with all missing variables listed."""
        # Arrange - missing multiple variables
        env_vars = {
            "JOB_ID": "test-job-id",
            # Missing WORKSPACE_ID and AGENT_INSTANCE_ID
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            with mock.patch(
                "agent_builder_sdk.env_var.retrieve_auth_token", return_value="test-auth-token"
            ):
                # Act & Assert
                with pytest.raises(ValueError) as exc_info:
                    get_agent_context_from_env()

                error_message = str(exc_info.value)
                assert "Missing required environment variables" in error_message
                assert "WORKSPACE_ID" in error_message
                assert "AGENT_INSTANCE_ID" in error_message

    def test_get_agent_context_uses_retrieve_auth_token(self):
        """Test that get_agent_context_from_env uses retrieve_auth_token for authorization."""
        # Arrange
        env_vars = {
            "JOB_ID": "test-job-id",
            "WORKSPACE_ID": "test-workspace-id",
            "AGENT_INSTANCE_ID": "test-agent-instance-id",
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            with mock.patch(
                "agent_builder_sdk.env_var.retrieve_auth_token", return_value="mocked-token"
            ) as mock_retrieve:
                # Act
                context = get_agent_context_from_env()

                # Assert
                mock_retrieve.assert_called_once()
                assert context.authorization_token == "mocked-token"


class TestRetrieveAuthToken:
    """Tests for retrieve_auth_token function"""

    def test_retrieve_auth_token_from_file_success(self):
        """Test successful token retrieval from file."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("ATX_AUTHZ_TOKEN=test-file-token")
            temp_file_path = temp_file.name

        try:
            env_vars = {"AUTH_TOKEN_FILE": temp_file_path}

            with mock.patch.dict(os.environ, env_vars, clear=True):
                # Act
                token = retrieve_auth_token()

                # Assert
                assert token == "test-file-token"
        finally:
            os.unlink(temp_file_path)

    def test_retrieve_auth_token_from_file_with_whitespace(self):
        """Test token retrieval from file with whitespace in token value."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("ATX_AUTHZ_TOKEN=  test-token-with-spaces  \n")
            temp_file_path = temp_file.name

        try:
            env_vars = {"AUTH_TOKEN_FILE": temp_file_path}

            with mock.patch.dict(os.environ, env_vars, clear=True):
                # Act
                token = retrieve_auth_token()

                # Assert
                assert (
                    token == "  test-token-with-spaces"
                )  # Token value preserves leading whitespace, trailing newline stripped
        finally:
            os.unlink(temp_file_path)

    def test_retrieve_auth_token_from_file_empty(self):
        """Test that empty file raises ValueError."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("")  # Empty file
            temp_file_path = temp_file.name

        try:
            env_vars = {"AUTH_TOKEN_FILE": temp_file_path}

            with mock.patch.dict(os.environ, env_vars, clear=True):
                # Act & Assert
                with pytest.raises(ValueError) as exc_info:
                    retrieve_auth_token()

                assert "ATX_AUTHZ_TOKEN not found in credentials file" in str(exc_info.value)
        finally:
            os.unlink(temp_file_path)

    def test_retrieve_auth_token_from_file_missing_key(self):
        """Test that file without ATX_AUTHZ_TOKEN key raises ValueError."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("SOME_OTHER_KEY=some-value")  # Wrong key format
            temp_file_path = temp_file.name

        try:
            env_vars = {"AUTH_TOKEN_FILE": temp_file_path}

            with mock.patch.dict(os.environ, env_vars, clear=True):
                # Act & Assert
                with pytest.raises(ValueError) as exc_info:
                    retrieve_auth_token()

                assert "ATX_AUTHZ_TOKEN not found in credentials file" in str(exc_info.value)
        finally:
            os.unlink(temp_file_path)

    def test_retrieve_auth_token_from_file_not_found(self):
        """Test that missing file raises ValueError."""
        # Arrange
        non_existent_path = "/path/that/does/not/exist"
        env_vars = {"AUTH_TOKEN_FILE": non_existent_path}

        with mock.patch.dict(os.environ, env_vars, clear=True):
            # Act & Assert
            with pytest.raises(ValueError) as exc_info:
                retrieve_auth_token()

            assert "AUTH_TOKEN_FILE env-var is not set or auth-token file is not found" in str(
                exc_info.value
            )

    def test_retrieve_auth_token_env_var_not_set(self):
        """Test that missing AUTH_TOKEN_FILE env var raises ValueError."""
        # Arrange - no AUTH_TOKEN_FILE set
        with mock.patch.dict(os.environ, {}, clear=True):
            # Act & Assert
            with pytest.raises(ValueError) as exc_info:
                retrieve_auth_token()

            assert "AUTH_TOKEN_FILE env-var is not set or auth-token file is not found" in str(
                exc_info.value
            )

    def test_retrieve_auth_token_from_file_io_error(self):
        """Test that IO errors raise ValueError."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("ATX_AUTHZ_TOKEN=test-token")
            temp_file_path = temp_file.name

        try:
            env_vars = {"AUTH_TOKEN_FILE": temp_file_path}

            with mock.patch.dict(os.environ, env_vars, clear=True):
                with mock.patch("builtins.open", side_effect=IOError("Permission denied")):
                    # Act & Assert
                    with pytest.raises(ValueError) as exc_info:
                        retrieve_auth_token()

                    error_message = str(exc_info.value)
                    assert "Failed to read auth token from file" in error_message
                    assert "Permission denied" in error_message
        finally:
            os.unlink(temp_file_path)


class TestGetBedrockSharedCapacityRoleArn:
    """Tests for get_bedrock_shared_capacity_role_arn function"""

    def test_returns_env_var_when_set(self):
        """Test that function returns environment variable when set."""
        test_arn = "arn:aws:iam::123456789012:role/CustomBedrockRole"

        with mock.patch.dict(os.environ, {"BEDROCK_SHARED_CAPACITY_ROLE_ARN": test_arn}):
            result = get_bedrock_shared_capacity_role_arn("us-east-1")
            assert result == test_arn

    def test_returns_iad_arn_for_us_east_1(self):
        """Test that function returns correct ARN for us-east-1 region."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = get_bedrock_shared_capacity_role_arn("us-east-1")
            expected = "arn:aws:iam::982081074531:role/BedrockSharedCapacityRole"
            assert result == expected

    def test_returns_iad_arn_for_us_west_2(self):
        """Test that function returns IAD account ARN for us-west-2 region."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = get_bedrock_shared_capacity_role_arn("us-west-2")
            expected = "arn:aws:iam::982081074531:role/BedrockSharedCapacityRole"
            assert result == expected

    def test_returns_none_for_unsupported_region(self):
        """Test that function returns None for unsupported regions."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = get_bedrock_shared_capacity_role_arn("eu-west-1")
            assert result is None

    def test_env_var_takes_precedence_over_region_mapping(self):
        """Test that environment variable takes precedence over region-based mapping."""
        custom_arn = "arn:aws:iam::999999999999:role/CustomRole"

        with mock.patch.dict(os.environ, {"BEDROCK_SHARED_CAPACITY_ROLE_ARN": custom_arn}):
            result = get_bedrock_shared_capacity_role_arn("us-east-1")
            assert result == custom_arn


class TestShouldUseProdBedrockCapacity:
    """Tests for should_use_prod_bedrock_capacity function"""

    def test_returns_false_when_disabled_via_disable_flag(self):
        """Test that function returns False when DISABLE_PROD_BEDROCK_CAPACITY is true."""
        with mock.patch.dict(os.environ, {"DISABLE_PROD_BEDROCK_CAPACITY": "true"}):
            result = should_use_prod_bedrock_capacity()
            assert result is False

    def test_returns_false_when_disabled_via_disable_flag_variants(self):
        """Test that function returns False for various disable flag values."""
        test_values = ["true", "1", "yes", "TRUE", "Yes"]

        for value in test_values:
            with mock.patch.dict(os.environ, {"DISABLE_PROD_BEDROCK_CAPACITY": value}):
                result = should_use_prod_bedrock_capacity()
                assert result is False, f"Failed for value: {value}"

    def test_returns_true_by_default(self):
        """Test that function returns True by default when no flags are set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = should_use_prod_bedrock_capacity()
            assert result is True

    def test_ignores_invalid_disable_flag_values(self):
        """Test that function ignores invalid values for disable flag."""
        invalid_values = ["false", "0", "no", "invalid", ""]

        for value in invalid_values:
            with mock.patch.dict(os.environ, {"DISABLE_PROD_BEDROCK_CAPACITY": value}):
                result = should_use_prod_bedrock_capacity()
                assert result is True, f"Should ignore invalid value: {value}"

    def test_validate_all_env_vars_present(self):
        """Test validation passes when all required env vars are present."""
        env_vars = {
            "AWS_REGION": "us-east-1",
            "STAGE": "prod",
            "WORKSPACE_ID": "test-workspace",
            "JOB_ID": "test-job",
            "AGENT_INSTANCE_ID": "test-agent",
        }

        with mock.patch.dict(os.environ, env_vars):
            validate_required_env_vars()


class TestGetInitialAgentRuntimeContextFromEnv:
    """Tests for get_initial_agent_runtime_context_from_env function."""

    def test_get_initial_agent_runtime_context_from_env_success(self):
        """Test successful creation of AgentRuntimeContext from environment variables."""
        env_vars = {
            "JOB_ID": "test-job-id",
            "WORKSPACE_ID": "test-workspace-id",
            "AGENT_INSTANCE_ID": "test-agent-instance-id",
            "AUTHORIZATION_TOKEN": "test-auth-token",
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            context = get_initial_agent_runtime_context_from_env()

            assert isinstance(context, AgentRuntimeContext)
            assert context.job_id == "test-job-id"
            assert context.workspace_id == "test-workspace-id"
            assert context.agent_instance_id == "test-agent-instance-id"
            assert context.initial_auth_token == "test-auth-token"

    def test_get_initial_agent_runtime_context_from_env_missing_vars(self):
        """Test that missing environment variables raise ValueError."""
        env_vars = {
            "JOB_ID": "test-job-id",
            # Missing required vars
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError):
                get_initial_agent_runtime_context_from_env()


class TestGetAgenticApiRequestContextWithCurrentToken:
    """Tests for get_agentic_api_request_context_with_current_token function."""

    def test_get_agentic_api_request_context_with_current_token_success(self):
        """Test successful creation of AgenticApiRequestContext with current token."""
        base_context = AgentRuntimeContext(
            workspace_id="test-workspace",
            job_id="test-job",
            agent_instance_id="test-agent",
            initial_auth_token="old-token",
        )

        with mock.patch(
            "agent_builder_sdk.env_var.retrieve_auth_token", return_value="current-token"
        ):
            result = get_agentic_api_request_context_with_current_token(base_context)

            assert isinstance(result, AgenticApiRequestContext)
            assert result.workspace_id == "test-workspace"
            assert result.job_id == "test-job"
            assert result.agent_instance_id == "test-agent"
            assert result.authorization_token == "current-token"  # Uses current token, not initial

    def test_get_agentic_api_request_context_with_current_token_no_token(self):
        """Test behavior when no current token is available."""
        base_context = AgentRuntimeContext(
            workspace_id="test-workspace", job_id="test-job", agent_instance_id="test-agent"
        )

        with mock.patch("agent_builder_sdk.env_var.retrieve_auth_token", return_value=None):
            result = get_agentic_api_request_context_with_current_token(base_context)

            assert isinstance(result, AgenticApiRequestContext)
            assert result.authorization_token is None


class TestSetRuntimeEnvVars:
    """Tests for set_runtime_env_vars function."""

    def test_set_runtime_env_vars_new_values(self):
        """Test setting new environment variables."""
        with mock.patch.dict(os.environ, {}, clear=True):
            set_runtime_env_vars("job-123", "ws-456", "agent-789")

            assert os.environ["JOB_ID"] == "job-123"
            assert os.environ["WORKSPACE_ID"] == "ws-456"
            assert os.environ["AGENT_INSTANCE_ID"] == "agent-789"

    def test_set_runtime_env_vars_overwrite(self, caplog):
        """Test overwriting existing environment variables."""
        with mock.patch.dict(
            os.environ,
            {"JOB_ID": "old-job", "WORKSPACE_ID": "old-ws", "AGENT_INSTANCE_ID": "old-agent"},
            clear=True,
        ):
            set_runtime_env_vars("new-job", "new-ws", "new-agent")

            assert os.environ["JOB_ID"] == "new-job"
            assert os.environ["WORKSPACE_ID"] == "new-ws"
            assert os.environ["AGENT_INSTANCE_ID"] == "new-agent"

            # Check warning logs
            assert "Overwriting JOB_ID from old-job to new-job" in caplog.text
            assert "Overwriting WORKSPACE_ID from old-ws to new-ws" in caplog.text
            assert "Overwriting AGENT_INSTANCE_ID from old-agent to new-agent" in caplog.text

    def test_set_runtime_env_vars_same_values(self, caplog):
        """Test setting same values (should not log warnings)."""
        with mock.patch.dict(
            os.environ,
            {"JOB_ID": "job-123", "WORKSPACE_ID": "ws-456", "AGENT_INSTANCE_ID": "agent-789"},
            clear=True,
        ):
            set_runtime_env_vars("job-123", "ws-456", "agent-789")

            assert os.environ["JOB_ID"] == "job-123"
            assert os.environ["WORKSPACE_ID"] == "ws-456"
            assert os.environ["AGENT_INSTANCE_ID"] == "agent-789"

            # Check no warning logs
            assert "Overwriting" not in caplog.text


class TestIsExternalAgenticApiEnabled:
    """Tests for the is_external_agentic_api_enabled function."""

    @mock.patch.dict(os.environ, {"USE_EXTERNAL_AGENTIC_API": "true"})
    def test_enabled_when_env_var_true(self):
        """Test function returns True when environment variable is 'true'."""
        assert is_external_agentic_api_enabled() is True

    @mock.patch.dict(os.environ, {"USE_EXTERNAL_AGENTIC_API": "false"})
    def test_disabled_when_env_var_false(self):
        """Test function returns False when environment variable is 'false'."""
        assert is_external_agentic_api_enabled() is False

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_disabled_when_env_var_missing(self):
        """Test function returns False when environment variable is missing."""
        assert is_external_agentic_api_enabled() is False
