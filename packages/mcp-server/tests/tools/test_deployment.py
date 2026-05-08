# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for deployment tools."""

import json
from unittest.mock import MagicMock, patch

from agent_builder_mcp.tools.deployment._build import (
    build_agent_image,
    get_container_runtime,
)
from agent_builder_mcp.tools.deployment._deploy import (
    _generate_runtime_name,
    deploy_agent_to_agentcore,
)
from agent_builder_mcp.tools.deployment._pipeline import (
    _check_logging_permissions,
    _get_default_execution_role_arn,
    _register_with_atx,
    deploy_agent_full_pipeline,
)

MODULE_BUILD = "agent_builder_mcp.tools.deployment._build"
MODULE_DEPLOY = "agent_builder_mcp.tools.deployment._deploy"
MODULE_PIPELINE = "agent_builder_mcp.tools.deployment._pipeline"


# --- Platform Detection Tests ---


class TestGetContainerRuntime:
    """Test container runtime detection."""

    def test_windows_returns_codebuild(self):
        """Test that Windows always returns 'codebuild'."""
        with patch("platform.system", return_value="Windows"):
            assert get_container_runtime() == "codebuild"

    def test_macos_with_finch(self):
        """Test that macOS with finch returns 'finch'."""
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", side_effect=lambda cmd: cmd == "finch"):
                assert get_container_runtime() == "finch"

    def test_macos_with_docker_no_finch(self):
        """Test that macOS without finch falls back to 'docker'."""
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", side_effect=lambda cmd: cmd == "docker"):
                assert get_container_runtime() == "docker"

    def test_linux_with_docker(self):
        """Test that Linux with docker returns 'docker'."""
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", side_effect=lambda cmd: cmd == "docker"):
                assert get_container_runtime() == "docker"

    def test_no_runtime_available(self):
        """Test that no runtime returns 'codebuild'."""
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value=None):
                assert get_container_runtime() == "codebuild"


# --- Build Tests ---


class TestBuildAgentImage:
    """Test build_agent_image function."""

    def test_missing_agent_directory(self):
        """Test error when agent directory doesn't exist."""
        result = json.loads(
            build_agent_image(agent_path="/nonexistent/path", agent_name="test-agent")
        )
        assert result["success"] is False
        assert "not found" in result["error"]
        assert result["error_type"] == "FileNotFoundError"

    def test_missing_dockerfile(self, tmp_path):
        """Test error when Dockerfile is missing."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()

        result = json.loads(build_agent_image(agent_path=str(agent_dir), agent_name="test-agent"))
        assert result["success"] is False
        assert "Dockerfile not found" in result["error"]
        assert result["error_type"] == "FileNotFoundError"

    def test_force_codebuild(self, tmp_path):
        """Test that use_codebuild=True forces CodeBuild."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_BUILD}._build_codebuild") as mock_codebuild:
            mock_codebuild.return_value = {
                "success": True,
                "image_uri": "test-uri",
                "build_method": "codebuild",
            }

            result = json.loads(
                build_agent_image(
                    agent_path=str(agent_dir), agent_name="test-agent", use_codebuild=True
                )
            )

            assert result["success"] is True
            assert result["build_method"] == "codebuild"
            mock_codebuild.assert_called_once()

    def test_auto_detect_finch(self, tmp_path):
        """Test auto-detection of finch runtime."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_BUILD}.get_container_runtime", return_value="finch"):
            with patch(f"{MODULE_BUILD}._build_local") as mock_build:
                mock_build.return_value = {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                }

                result = json.loads(
                    build_agent_image(
                        agent_path=str(agent_dir), agent_name="test-agent", use_codebuild=False
                    )
                )

                assert result["success"] is True
                assert result["build_method"] == "finch"
                mock_build.assert_called_once()


# --- Deploy Tests ---


class TestGenerateRuntimeName:
    """Test runtime name generation."""

    def test_basic_name_generation(self):
        """Test basic runtime name format."""
        name = _generate_runtime_name("test-agent")
        assert name.startswith("atx_ws_test_agent_")
        assert len(name) <= 48
        # Check timestamp format (10 digits: MMDDHHmmss)
        timestamp = name.split("_")[-1]
        assert len(timestamp) == 10
        assert timestamp.isdigit()

    def test_replaces_hyphens(self):
        """Test that hyphens are replaced with underscores."""
        name = _generate_runtime_name("my-agent-name")
        assert "-" not in name
        assert "my_agent_name" in name

    def test_truncates_long_names(self):
        """Test that long names are truncated to 48 characters."""
        long_name = "a" * 100
        name = _generate_runtime_name(long_name)
        assert len(name) <= 48


class TestDeployAgentToAgentCore:
    """Test deploy_agent_to_agentcore function."""

    def test_successful_deployment(self):
        """Test successful AgentCore deployment."""
        mock_client = MagicMock()
        mock_client.create_agent_runtime.return_value = {
            "agentRuntimeId": "test-runtime-id",
            "agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
        }
        mock_client.get_agent_runtime.return_value = {"status": "ACTIVE"}

        with patch(f"{MODULE_DEPLOY}.boto3.client", return_value=mock_client):
            result = json.loads(
                deploy_agent_to_agentcore(
                    image_uri="123456.dkr.ecr.us-east-1.amazonaws.com/test:latest",
                    agent_name="test-agent",
                    execution_role_arn="arn:aws:iam::123:role/TestRole",
                )
            )

            assert result["success"] is True
            assert result["runtime_id"] == "test-runtime-id"
            assert result["status"] == "ACTIVE"

    def test_deployment_failure(self):
        """Test AgentCore deployment failure."""
        mock_client = MagicMock()
        mock_client.create_agent_runtime.return_value = {
            "agentRuntimeId": "test-runtime-id",
            "agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
        }
        mock_client.get_agent_runtime.return_value = {"status": "FAILED"}

        with patch(f"{MODULE_DEPLOY}.boto3.client", return_value=mock_client):
            result = json.loads(
                deploy_agent_to_agentcore(
                    image_uri="123456.dkr.ecr.us-east-1.amazonaws.com/test:latest",
                    agent_name="test-agent",
                    execution_role_arn="arn:aws:iam::123:role/TestRole",
                    timeout_seconds=1,
                )
            )

            assert result["success"] is False
            assert "FAILED" in result.get("error", "")


# --- Execution Role Detection & Permission Check Tests ---


class TestGetDefaultExecutionRoleArn:
    """Test auto-detection of AgentCoreExecutionRole."""

    def test_returns_arn_when_sts_succeeds(self):
        """Test successful role detection returns ARN."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}

        with patch(f"{MODULE_PIPELINE}.boto3.client", return_value=mock_sts):
            result = _get_default_execution_role_arn()

        assert result == "arn:aws:iam::XXXXXXXXXXXX:role/AgentCoreExecutionRole"

    def test_returns_none_when_sts_fails(self):
        """Test returns None when STS call fails."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("ExpiredToken")

        with patch(f"{MODULE_PIPELINE}.boto3.client", return_value=mock_sts):
            result = _get_default_execution_role_arn()

        assert result is None


class TestCheckLoggingPermissions:
    """Test _check_logging_permissions helper."""

    def test_all_permissions_present(self):
        """Test returns empty list when all permissions are allowed."""
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.return_value = {
            "EvaluationResults": [
                {"EvalActionName": "logs:DescribeLogStreams", "EvalDecision": "allowed"},
            ]
        }

        missing = _check_logging_permissions(
            mock_iam, "arn:aws:iam::123:role/Test", "123", "us-east-1"
        )
        assert missing == []

    def test_partial_permissions_missing(self):
        """Test returns only the denied action."""
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = [
            {
                "EvaluationResults": [
                    {"EvalActionName": "logs:DescribeLogStreams", "EvalDecision": "allowed"},
                ]
            },
            {
                "EvaluationResults": [
                    {"EvalActionName": "logs:DescribeLogGroups", "EvalDecision": "implicitDeny"},
                ]
            },
        ]

        missing = _check_logging_permissions(
            mock_iam, "arn:aws:iam::123:role/Test", "123", "us-east-1"
        )
        assert missing == ["logs:DescribeLogGroups"]

    def test_simulate_api_denied_returns_empty(self):
        """Test graceful fallback when caller lacks SimulatePrincipalPolicy."""
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.side_effect = Exception("AccessDenied")

        missing = _check_logging_permissions(
            mock_iam, "arn:aws:iam::123:role/Test", "123", "us-east-1"
        )
        assert missing == []

    def test_resource_arns_are_scoped_correctly(self):
        """Test that simulate calls use the correct resource ARN per action."""
        mock_iam = MagicMock()
        mock_iam.simulate_principal_policy.return_value = {"EvaluationResults": []}

        _check_logging_permissions(mock_iam, "arn:aws:iam::999:role/Test", "999", "eu-west-1")

        assert mock_iam.simulate_principal_policy.call_count == 2
        mock_iam.simulate_principal_policy.assert_any_call(
            PolicySourceArn="arn:aws:iam::999:role/Test",
            ActionNames=["logs:DescribeLogStreams"],
            ResourceArns=["arn:aws:logs:eu-west-1:999:log-group:/aws/bedrock-agentcore/runtimes/*"],
        )
        mock_iam.simulate_principal_policy.assert_any_call(
            PolicySourceArn="arn:aws:iam::999:role/Test",
            ActionNames=["logs:DescribeLogGroups"],
            ResourceArns=["arn:aws:logs:eu-west-1:999:log-group:*"],
        )


# --- Pipeline Tests ---


class TestDeployAgentFullPipeline:
    """Test full deployment pipeline."""

    def test_build_phase_failure(self, tmp_path):
        """Test pipeline stops on build phase failure."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        # No Dockerfile - should fail

        result = json.loads(
            deploy_agent_full_pipeline(agent_path=str(agent_dir), agent_name="test-agent")
        )

        assert result["success"] is False
        assert result["phase"] == "build"

    def test_deploy_phase_failure(self, tmp_path):
        """Test pipeline stops on deploy phase failure."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        # Mock successful build but failed deploy
        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {"success": False, "error": "Deployment failed"}
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_role:
                    mock_role.return_value = "arn:aws:iam::123:role/TestRole"

                    with patch(f"{MODULE_PIPELINE}._check_logging_permissions", return_value=[]):

                        result = json.loads(
                            deploy_agent_full_pipeline(
                                agent_path=str(agent_dir), agent_name="test-agent"
                            )
                        )

                    assert result["success"] is False
                    assert result["phase"] == "deploy"

    def test_successful_full_pipeline(self, tmp_path):
        """Test successful full pipeline execution."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        # Mock all phases as successful
        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {
                        "success": True,
                        "runtime_id": "test-runtime",
                        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                        "runtime_name": "test_runtime",
                        "status": "ACTIVE",
                    }
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_exec_role:
                    mock_exec_role.return_value = "arn:aws:iam::123:role/ExecRole"

                    with patch(f"{MODULE_PIPELINE}._check_logging_permissions", return_value=[]):

                        with patch(f"{MODULE_PIPELINE}._register_with_atx") as mock_register:
                            mock_register.return_value = {
                                "success": True,
                                "agent_name": "test-agent",
                                "version": "1.0.0",
                            }

                            with patch(
                                f"{MODULE_PIPELINE}._get_default_access_role_arn"
                            ) as mock_access_role:
                                mock_access_role.return_value = "arn:aws:iam::123:role/AccessRole"

                                result = json.loads(
                                    deploy_agent_full_pipeline(
                                        agent_path=str(agent_dir), agent_name="test-agent"
                                    )
                                )

                                assert result["success"] is True
                                assert "build" in result["phases"]
                                assert "deploy" in result["phases"]
                                assert "register" in result["phases"]

    def test_missing_logging_permissions_warns_but_continues(self, tmp_path):
        """Test pipeline warns but continues when permission pre-check reports missing permissions."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {
                        "success": True,
                        "runtime_id": "test-runtime",
                        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                        "runtime_name": "test_runtime",
                        "status": "ACTIVE",
                    }
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_role:
                    mock_role.return_value = "arn:aws:iam::XXXXXXXXXXXX:role/AgentCoreExecutionRole"

                    with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                        mock_sts = MagicMock()
                        mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                        mock_iam = MagicMock()
                        mock_boto3.client.side_effect = lambda svc, **kw: (
                            mock_sts if svc == "sts" else mock_iam
                        )

                        with patch(f"{MODULE_PIPELINE}._check_logging_permissions") as mock_check:
                            mock_check.return_value = [
                                "logs:DescribeLogStreams",
                                "logs:DescribeLogGroups",
                            ]

                            with patch(
                                f"{MODULE_PIPELINE}._get_default_access_role_arn"
                            ) as mock_access:
                                mock_access.return_value = "arn:aws:iam::123:role/AccessRole"

                                with patch(f"{MODULE_PIPELINE}._register_with_atx") as mock_reg:
                                    mock_reg.return_value = {
                                        "success": True,
                                        "agent_name": "test-agent",
                                        "version": "1.0.0",
                                    }

                                    result = json.loads(
                                        deploy_agent_full_pipeline(
                                            agent_path=str(agent_dir),
                                            agent_name="test-agent",
                                        )
                                    )

                                    # Pipeline should proceed despite permission warning
                                    assert result["success"] is True
                                    # Deploy phase was called (not short-circuited)
                                    mock_deploy.assert_called_once()

    def test_permission_check_exception_does_not_block(self, tmp_path):
        """Test pipeline continues if the permission check itself throws (e.g. AccessDenied on STS)."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {
                        "success": True,
                        "runtime_id": "test-runtime",
                        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                        "runtime_name": "test_runtime",
                        "status": "ACTIVE",
                    }
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_role:
                    mock_role.return_value = "arn:aws:iam::123:role/TestRole"

                    # boto3.client("sts") inside the permission check block throws
                    with patch(
                        f"{MODULE_PIPELINE}.boto3.client", side_effect=Exception("AccessDenied")
                    ):

                        with patch(
                            f"{MODULE_PIPELINE}._get_default_access_role_arn"
                        ) as mock_access:
                            mock_access.return_value = "arn:aws:iam::123:role/AccessRole"

                            with patch(f"{MODULE_PIPELINE}._register_with_atx") as mock_register:
                                mock_register.return_value = {
                                    "success": True,
                                    "agent_name": "test-agent",
                                    "version": "1.0.0",
                                }

                                result = json.loads(
                                    deploy_agent_full_pipeline(
                                        agent_path=str(agent_dir), agent_name="test-agent"
                                    )
                                )

                                # Pipeline should still succeed — permission check is best-effort
                                assert result["success"] is True

    def test_skip_registry_option(self, tmp_path):
        """Test skip_registry parameter."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {
                        "success": True,
                        "runtime_id": "test-runtime",
                        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                        "runtime_name": "test_runtime",
                        "status": "ACTIVE",
                    }
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_role:
                    mock_role.return_value = "arn:aws:iam::123:role/TestRole"

                    with patch(f"{MODULE_PIPELINE}._check_logging_permissions", return_value=[]):

                        result = json.loads(
                            deploy_agent_full_pipeline(
                                agent_path=str(agent_dir),
                                agent_name="test-agent",
                                skip_registry=True,
                            )
                        )

                        assert result["success"] is True
                        assert result["phases"]["register"]["skipped"] is True

    def test_access_role_autodetect_failure_skips_registration(self, tmp_path):
        """Test that failed access role auto-detect skips registration but pipeline succeeds."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "Dockerfile").write_text("FROM scratch")

        with patch(f"{MODULE_PIPELINE}.build_agent_image") as mock_build:
            mock_build.return_value = json.dumps(
                {
                    "success": True,
                    "image_uri": "test-uri",
                    "build_method": "finch",
                    "ecr_repository": "test-repo",
                }
            )

            with patch(f"{MODULE_PIPELINE}.deploy_agent_to_agentcore") as mock_deploy:
                mock_deploy.return_value = json.dumps(
                    {
                        "success": True,
                        "runtime_id": "test-runtime",
                        "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                        "runtime_name": "test_runtime",
                        "status": "ACTIVE",
                    }
                )

                with patch(f"{MODULE_PIPELINE}._get_default_execution_role_arn") as mock_exec_role:
                    mock_exec_role.return_value = "arn:aws:iam::123:role/ExecRole"

                    with patch(f"{MODULE_PIPELINE}._check_logging_permissions", return_value=[]):

                        with patch(
                            f"{MODULE_PIPELINE}._get_default_access_role_arn"
                        ) as mock_access_role:
                            mock_access_role.return_value = None

                            with patch(f"{MODULE_PIPELINE}._register_with_atx") as mock_register:
                                result = json.loads(
                                    deploy_agent_full_pipeline(
                                        agent_path=str(agent_dir),
                                        agent_name="test-agent",
                                    )
                                )

                                assert result["success"] is True
                                assert result["phases"]["register"]["skipped"] is True
                                assert "auto-detect" in result["phases"]["register"]["reason"]
                                mock_register.assert_not_called()


# --- _register_with_atx Unit Tests ---


class TestRegisterWithAtx:
    """Test _register_with_atx internal function directly.

    Previous implementation used a lazy import of a non-existent module
    (registry._register) that was always mocked away in pipeline tests,
    hiding the ImportError until runtime. These tests exercise the real
    function body to catch such regressions.
    """

    def test_imports_resolve(self):
        """Verify _pipeline module imports resolve — catches dead imports at collection time.

        The original bug was a lazy import of a non-existent module hidden inside
        a try/except. Now that registry_client is a top-level import in _pipeline.py,
        a broken import would fail at test collection. This test documents that contract.
        """
        from agent_builder_mcp.tools.deployment._pipeline import registry_client  # noqa: F401

    def test_successful_registration(self):
        """Test _register_with_atx executes all three steps with mocked client."""
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = type("ConflictException", (Exception,), {})

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                result = _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                    access_role_arn="arn:aws:iam::123:role/AccessRole",
                    registry_endpoint="https://test.endpoint",
                )

        assert result["success"] is True
        assert result["agent_name"] == "test-agent"
        mock_client.register_agent.assert_called_once()
        mock_client.publish_agent_version.assert_called_once()
        mock_client.update_publisher_access_control.assert_called_once()

    def test_conflict_on_register_continues_to_publish(self):
        """Test that ConflictException on register is handled gracefully."""
        mock_client = MagicMock()
        conflict_exc = type("ConflictException", (Exception,), {})
        mock_client.exceptions.ConflictException = conflict_exc
        mock_client.register_agent.side_effect = conflict_exc("already exists")

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                result = _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                    access_role_arn="arn:aws:iam::123:role/AccessRole",
                    registry_endpoint="https://test.endpoint",
                )

        assert result["success"] is True
        # Still published despite register conflict
        mock_client.publish_agent_version.assert_called_once()

    def test_conflict_on_publish_continues_to_access_control(self):
        """Test that ConflictException on publish is handled gracefully (re-deploy same version)."""
        mock_client = MagicMock()
        conflict_exc = type("ConflictException", (Exception,), {})
        mock_client.exceptions.ConflictException = conflict_exc
        mock_client.publish_agent_version.side_effect = conflict_exc("version already exists")

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                result = _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:test",
                    access_role_arn="arn:test",
                    registry_endpoint="https://test",
                )

        assert result["success"] is True
        mock_client.update_publisher_access_control.assert_called_once()

    def test_orchestrator_metadata_included(self):
        """Test that job_orchestrator=True includes jobOrchestratorMetadata."""
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = type("ConflictException", (Exception,), {})

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                _register_with_atx(
                    agent_name="test-orch",
                    agent_version="1.0.0",
                    runtime_arn="arn:test",
                    access_role_arn="arn:test",
                    registry_endpoint="https://test",
                    job_orchestrator=True,
                    chat_ui_label="Test Orchestrator",
                    chat_agent_identifier="test-orch",
                )

        call_kwargs = mock_client.register_agent.call_args
        metadata = call_kwargs.kwargs.get("metadata") or call_kwargs[1].get("metadata")
        assert metadata["type"] == "ORCHESTRATOR_AGENT"
        assert metadata["jobOrchestrator"] is True
        assert metadata["jobOrchestratorMetadata"]["chatUILabel"] == "Test Orchestrator"

    def test_agent_card_populated(self):
        """Test that agentCard is populated with agent identity and required extensions."""
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = type("ConflictException", (Exception,), {})

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                _register_with_atx(
                    agent_name="test-agent",
                    agent_version="2.0.0",
                    runtime_arn="arn:test",
                    access_role_arn="arn:test",
                    registry_endpoint="https://test",
                )

        call_kwargs = mock_client.publish_agent_version.call_args
        config = call_kwargs.kwargs.get("configuration") or call_kwargs[1].get("configuration")
        card = config["agentCard"]

        assert card["id"] == "test-agent"
        assert card["name"] == "test-agent"
        assert card["version"] == "2.0.0"

        # accountId populated from STS
        provider = card["capabilities"]["extensions"][0]
        assert provider["name"] == "Agent Provider"
        assert provider["params"]["accountId"] == "XXXXXXXXXXXX"

        # All three required extensions present
        ext_names = [e["name"] for e in card["capabilities"]["extensions"]]
        assert ext_names == ["Agent Provider", "Agent Dependencies", "Agent Connectors"]

    def test_access_control_conflict_is_non_fatal(self):
        """Test that ConflictException on access control is non-fatal (already enabled)."""
        mock_client = MagicMock()
        conflict_exc = type("ConflictException", (Exception,), {})
        mock_client.exceptions.ConflictException = conflict_exc
        mock_client.update_publisher_access_control.side_effect = conflict_exc("already enabled")

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                result = _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:test",
                    access_role_arn="arn:test",
                    registry_endpoint="https://test",
                )

        assert result["success"] is True

    def test_access_control_validation_error_is_fatal(self):
        """Test that ValidationException on access control propagates as failure.

        Unlike ConflictException, ValidationException (e.g. allowlist at capacity)
        means the agent is registered but no account can use it.
        """
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = type("ConflictException", (Exception,), {})
        mock_client.update_publisher_access_control.side_effect = Exception(
            "ValidationException: allowlist at capacity"
        )

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                result = _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:test",
                    access_role_arn="arn:test",
                    registry_endpoint="https://test",
                )

        assert result["success"] is False
        assert "ValidationException" in result["error"]

    def test_compute_configuration_includes_arns(self):
        """Test that computeConfiguration includes runtimeArn and atxAccessRoleArn."""
        mock_client = MagicMock()
        mock_client.exceptions.ConflictException = type("ConflictException", (Exception,), {})

        with patch(f"{MODULE_PIPELINE}.registry_client", return_value=mock_client):
            with patch(f"{MODULE_PIPELINE}.boto3") as mock_boto3:
                mock_sts = MagicMock()
                mock_sts.get_caller_identity.return_value = {"Account": "XXXXXXXXXXXX"}
                mock_boto3.client.return_value = mock_sts

                _register_with_atx(
                    agent_name="test-agent",
                    agent_version="1.0.0",
                    runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
                    access_role_arn="arn:aws:iam::123:role/AccessRole",
                    registry_endpoint="https://test",
                )

        call_kwargs = mock_client.publish_agent_version.call_args
        config = call_kwargs.kwargs.get("configuration") or call_kwargs[1].get("configuration")
        ac = config["computeConfiguration"]["provisionedComputeConfiguration"]["agentCoreConfiguration"]
        assert ac["runtimeArn"] == "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test"
        assert ac["atxAccessRoleArn"] == "arn:aws:iam::123:role/AccessRole"

        # Required schema and prompt fields
        assert config["inputPayloadSchema"] == {}
        assert config["outputPayloadSchema"] == {}
        assert config["objectiveNegotiationPrompt"] == ""


# --- MCP Registration Tests ---


class TestRegistration:
    """Test MCP tool registration."""

    def test_tools_registered(self):
        """Test that deployment tools are registered."""
        from mcp.server.fastmcp import FastMCP

        from agent_builder_mcp.tools.deployment import register_deployment_tools

        mcp = FastMCP(name="test")
        register_deployment_tools(mcp)

        tools = mcp._tool_manager._tools
        assert "build_agent_image" in tools
        assert "deploy_agent_to_agentcore" in tools
        assert "deploy_agent_full_pipeline" in tools
