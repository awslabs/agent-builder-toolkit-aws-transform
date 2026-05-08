# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build agent Docker images."""

import json
import logging
import platform
import shutil
import subprocess
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_container_runtime() -> str:
    """
    Auto-detect best container runtime for current platform.

    Detection order:
    1. Windows → return "codebuild" (force CodeBuild, finch not available)
    2. Check for finch command → return "finch" (preferred on macOS/Linux)
    3. Check for docker command → return "docker" (fallback)
    4. None available → return "codebuild" (cloud fallback)

    Returns:
        "finch", "docker", or "codebuild"
    """
    if platform.system() == "Windows":
        # Windows: finch not available, force CodeBuild
        logger.info("Detected Windows platform, using CodeBuild")
        return "codebuild"

    # macOS/Linux: prefer finch over docker
    if shutil.which("finch"):
        logger.info("Detected finch runtime")
        return "finch"
    elif shutil.which("docker"):
        logger.info("Detected docker runtime")
        return "docker"
    else:
        # No local runtime, fall back to CodeBuild
        logger.info("No local container runtime found, using CodeBuild")
        return "codebuild"


def _get_ecr_uri(agent_name: str, region: str = "us-east-1") -> str:
    """
    Get or create ECR repository URI for agent.

    Args:
        agent_name: Agent name for ECR repository
        region: AWS region

    Returns:
        ECR repository URI (e.g., 123456.dkr.ecr.us-east-1.amazonaws.com/atx-workshop/agent-name)
    """
    ecr = boto3.client("ecr", region_name=region)
    repo_name = f"atx-workshop/{agent_name}"

    try:
        response = ecr.describe_repositories(repositoryNames=[repo_name])
        repo_uri = response["repositories"][0]["repositoryUri"]
        logger.info(f"Using existing ECR repository: {repo_uri}")
        return repo_uri
    except ClientError as e:
        if e.response["Error"]["Code"] == "RepositoryNotFoundException":
            # Create repository
            logger.info(f"Creating ECR repository: {repo_name}")
            response = ecr.create_repository(
                repositoryName=repo_name,
                imageScanningConfiguration={"scanOnPush": True},
            )
            repo_uri = response["repository"]["repositoryUri"]
            logger.info(f"Created ECR repository: {repo_uri}")
            return repo_uri
        raise


def _ecr_login(runtime: str, region: str = "us-east-1") -> None:
    """
    Authenticate container runtime with ECR.

    Args:
        runtime: Container runtime ("finch" or "docker")
        region: AWS region
    """
    ecr = boto3.client("ecr", region_name=region)
    auth = ecr.get_authorization_token()
    token = auth["authorizationData"][0]["authorizationToken"]
    endpoint = auth["authorizationData"][0]["proxyEndpoint"]

    # Decode token (format: username:password)
    import base64

    decoded = base64.b64decode(token).decode("utf-8")
    username, password = decoded.split(":", 1)

    # Login to ECR
    login_cmd = [runtime, "login", "--username", username, "--password-stdin", endpoint]

    logger.info(f"Logging in to ECR with {runtime}")
    subprocess.run(login_cmd, input=password.encode(), check=True, capture_output=True)


def _build_local(
    agent_path: Path, agent_name: str, runtime: str, region: str = "us-east-1"
) -> dict:
    """
    Build agent image locally using finch or docker.

    Args:
        agent_path: Path to agent directory
        agent_name: Agent name
        runtime: Container runtime ("finch" or "docker")
        region: AWS region

    Returns:
        Build result dict
    """
    try:
        # Get ECR URI
        ecr_uri = _get_ecr_uri(agent_name, region)
        image_tag = f"{ecr_uri}:latest"

        # Build image
        logger.info(f"Building image with {runtime}: {image_tag}")
        build_cmd = [
            runtime,
            "build",
            "--platform",
            "linux/arm64",
            "-f",
            str(agent_path / "Dockerfile"),
            "-t",
            image_tag,
            str(agent_path),
        ]

        result = subprocess.run(build_cmd, check=True, capture_output=True, text=True)
        logger.debug(f"Build output: {result.stdout}")

        # Login to ECR
        _ecr_login(runtime, region)

        # Push to ECR
        logger.info(f"Pushing image to ECR: {image_tag}")
        push_cmd = [runtime, "push", image_tag]
        result = subprocess.run(push_cmd, check=True, capture_output=True, text=True)
        logger.debug(f"Push output: {result.stdout}")

        return {
            "success": True,
            "image_uri": image_tag,
            "build_method": runtime,
            "image_tag": "latest",
            "ecr_repository": f"atx-workshop/{agent_name}",
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Build command failed: {e.stderr}")
        return {
            "success": False,
            "error": f"Build failed: {e.stderr}",
            "error_type": "BuildError",
            "command": " ".join(e.cmd),
            "exit_code": e.returncode,
        }


def _build_codebuild(agent_path: Path, agent_name: str, region: str = "us-east-1") -> dict:
    """
    Build agent image using AWS CodeBuild.

    Args:
        agent_path: Path to agent directory
        agent_name: Agent name
        region: AWS region

    Returns:
        Build result dict
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)

        # Get ECR URI
        ecr_uri = _get_ecr_uri(agent_name, region)

        # Trigger CodeBuild
        logger.info("Triggering CodeBuild project: atx-agent-builder")
        build_response = codebuild.start_build(
            projectName="atx-agent-builder",
            environmentVariablesOverride=[
                {"name": "AGENT_PATH", "value": str(agent_path.absolute())},
                {"name": "AGENT_NAME", "value": agent_name},
                {"name": "ECR_REPO", "value": f"atx-workshop/{agent_name}"},
                {"name": "IMAGE_TAG", "value": "latest"},
            ],
        )

        build_id = build_response["build"]["id"]
        logger.info(f"CodeBuild started: {build_id}")

        # Poll for completion
        max_wait = 600  # 10 minutes
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            status_response = codebuild.batch_get_builds(ids=[build_id])
            build = status_response["builds"][0]
            status = build["buildStatus"]

            logger.info(f"CodeBuild status: {status} (elapsed: {elapsed}s)")

            if status == "SUCCEEDED":
                return {
                    "success": True,
                    "image_uri": f"{ecr_uri}:latest",
                    "build_method": "codebuild",
                    "image_tag": "latest",
                    "ecr_repository": f"atx-workshop/{agent_name}",
                    "build_id": build_id,
                    "build_duration_seconds": elapsed,
                }
            elif status in ["FAILED", "FAULT", "STOPPED", "TIMED_OUT"]:
                return {
                    "success": False,
                    "error": f"CodeBuild failed with status: {status}",
                    "error_type": "BuildError",
                    "build_id": build_id,
                    "logs": build.get("logs", {}).get("deepLink"),
                }

        # Timeout
        return {
            "success": False,
            "error": "CodeBuild timeout (10 minutes)",
            "error_type": "TimeoutError",
            "build_id": build_id,
        }

    except ClientError as e:
        logger.error(f"CodeBuild error: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "CodeBuildError",
            "hint": "Ensure atx-agent-builder CodeBuild project exists and you have permissions",
        }


def build_agent_image(
    agent_path: str, agent_name: str, use_codebuild: bool = False, region: str = "us-east-1"
) -> str:
    """
    Build ATX agent Docker image for ARM64 platform.

    Supports three build methods:
    1. Local finch (preferred on macOS/Linux)
    2. Local docker (fallback)
    3. AWS CodeBuild (required for Windows, optional for others)

    Args:
        agent_path: Path to agent directory containing Dockerfile (e.g., "./agents/modernization")
        agent_name: Agent name for ECR repository naming (e.g., "modernization-orchestrator")
        use_codebuild: Force CodeBuild even if local runtime available (default: False)
        region: AWS region (default: "us-east-1")

    Returns:
        JSON string with build result:
        {
            "success": true,
            "image_uri": "123456789.dkr.ecr.us-east-1.amazonaws.com/atx-workshop/agent-name:latest",
            "build_method": "finch" | "docker" | "codebuild",
            "image_tag": "latest",
            "ecr_repository": "atx-workshop/agent-name"
        }

    Errors:
        - FileNotFoundError: Dockerfile not found in agent_path
        - RuntimeError: No container runtime available and CodeBuild not requested
        - subprocess.CalledProcessError: Build command failed
    """
    try:
        # Validate inputs
        agent_dir = Path(agent_path).expanduser().resolve()
        if not agent_dir.exists():
            return json.dumps(
                {
                    "success": False,
                    "error": f"Agent directory not found: {agent_path}",
                    "error_type": "FileNotFoundError",
                },
                indent=2,
            )

        dockerfile = agent_dir / "Dockerfile"
        if not dockerfile.exists():
            return json.dumps(
                {
                    "success": False,
                    "error": f"Dockerfile not found in {agent_path}",
                    "error_type": "FileNotFoundError",
                    "hint": "Make sure your agent directory contains a Dockerfile",
                },
                indent=2,
            )

        # Determine build method
        if use_codebuild:
            build_method = "codebuild"
        else:
            build_method = get_container_runtime()

        logger.info(f"Building agent '{agent_name}' using method: {build_method}")

        # Execute build
        if build_method == "codebuild":
            result = _build_codebuild(agent_dir, agent_name, region)
        elif build_method in ["finch", "docker"]:
            result = _build_local(agent_dir, agent_name, build_method, region)
        else:
            return json.dumps(
                {
                    "success": False,
                    "error": "No container runtime available",
                    "error_type": "RuntimeError",
                    "hint": "Install finch or docker, or use use_codebuild=True",
                },
                indent=2,
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.exception("Unexpected error in build_agent_image")
        return json.dumps(
            {"success": False, "error": str(e), "error_type": type(e).__name__}, indent=2
        )
