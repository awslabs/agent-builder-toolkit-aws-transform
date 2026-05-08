# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Skill operations tools."""

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

import requests  # type: ignore[import-untyped]
from mcp.server.fastmcp import FastMCP

from ..registry._client import registry_client


def register_skill_operations_tools(mcp: FastMCP) -> None:
    """Register skill operations tools with MCP server."""
    mcp.tool(description="List all skills registered by the caller")(list_skills)
    mcp.tool(description="Retrieve metadata for a specific skill")(get_skill_metadata)
    mcp.tool(description="Update metadata for a specific skill")(update_skill_metadata)
    mcp.tool(description="Upload a skill artifact from a local file or directory")(upload_skill)
    mcp.tool(description="Download a skill artifact from the registry")(download_skill)
    mcp.tool(description="List AWS account IDs with access to a skill")(list_skill_access_control)
    mcp.tool(description="Enable or disable access for an AWS account to a skill")(
        update_skill_access_control
    )


def list_skills(filter: Optional[dict[str, str]] = None) -> str:
    """List all skills registered by the caller. Auto-paginates."""
    try:
        client = registry_client()
        all_skills: list[Any] = []
        next_token: Optional[str] = None
        while True:
            kwargs: dict[str, Any] = {}
            if filter:
                kwargs["filter"] = filter
            if next_token:
                kwargs["nextToken"] = next_token
            response = client.list_skills(**kwargs)
            all_skills.extend(response.get("skills", []))
            next_token = response.get("nextToken")
            if not next_token:
                break
        return json.dumps({"skills": all_skills}, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_skill_metadata(skill_name: str) -> str:
    """Retrieve metadata for a specific skill."""
    try:
        client = registry_client()
        response = client.get_skill_metadata(skillName=skill_name)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def update_skill_metadata(
    skill_name: str,
    description: Optional[str] = None,
    skill_version_data: Optional[dict[str, Any]] = None,
    visibility: Optional[str] = None,
    deprecate: Optional[bool] = None,
) -> str:
    """Update metadata for a specific skill."""
    try:
        client = registry_client()
        kwargs: dict[str, Any] = {"skillName": skill_name, "idempotencyToken": str(uuid.uuid4())}
        if description is not None:
            kwargs["description"] = description
        if skill_version_data is not None:
            kwargs["skillVersionData"] = skill_version_data
        if visibility is not None:
            kwargs["visibility"] = visibility
        if deprecate is not None:
            kwargs["deprecate"] = deprecate
        response = client.update_skill_metadata(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def upload_skill(
    skill_name: str,
    description: str,
    file_path: str,
    version: str = "1.0.0",
    visibility: Optional[str] = None,
) -> str:
    """Upload a skill artifact from a local file or directory path."""
    try:
        import hashlib

        client = registry_client()
        path = Path(file_path)

        # Zip if directory or non-zip file
        if path.is_dir():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
                for f in path.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(path))
            file_content = buf.getvalue()
        else:
            file_content = path.read_bytes()
            if not file_content[:4] == b"PK\x03\x04":
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
                    zf.writestr(path.name, file_content)
                file_content = buf.getvalue()

        # Compute SHA-256 digest
        import base64

        sha256_hash = base64.b64encode(hashlib.sha256(file_content).digest()).decode()

        # Get presigned upload URL
        upload_kwargs: dict[str, Any] = {
            "skillName": skill_name,
            "version": version,
            "description": description,
            "contentDigest": {"sha256": sha256_hash},
            "idempotencyToken": str(uuid.uuid4()),
        }
        if visibility:
            upload_kwargs["visibility"] = visibility
        url_response = client.create_skill_upload_url(**upload_kwargs)

        # Upload
        headers = {
            k: ",".join(v) if isinstance(v, list) else v
            for k, v in url_response["requestHeaders"].items()
        }
        requests.put(
            url_response["s3PreSignedUrl"], data=file_content, headers=headers
        ).raise_for_status()

        # Activate
        client.update_skill_metadata(
            skillName=skill_name,
            skillVersionData={"version": version, "status": "ACTIVE"},
            idempotencyToken=str(uuid.uuid4()),
        )

        return json.dumps({"message": f"Skill '{skill_name}' uploaded and activated"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def download_skill(
    skill_name: str,
    file_path: str,
    unzip: bool = False,
) -> str:
    """Download a skill artifact from the registry."""
    try:
        client = registry_client()
        url_response = client.create_skill_download_url(
            skillName=skill_name,
            idempotencyToken=str(uuid.uuid4()),
        )

        headers = {
            k: ",".join(v) if isinstance(v, list) else v
            for k, v in url_response["requestHeaders"].items()
        }
        resp = requests.get(url_response["s3PreSignedUrl"], headers=headers)
        resp.raise_for_status()
        data = resp.content

        if unzip and data[:4] == b"PK\x03\x04":
            out_dir = Path(file_path) / skill_name
            out_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(out_dir)
            files = [str(f.relative_to(out_dir)) for f in out_dir.rglob("*") if f.is_file()]
            return json.dumps(
                {"message": f"Extracted skill to {out_dir}", "files": files}, indent=2
            )

        Path(file_path).write_bytes(data)
        return json.dumps({"message": f"Downloaded skill to {file_path}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_skill_access_control(skill_name: str) -> str:
    """List AWS account IDs that have been granted access to a skill."""
    try:
        client = registry_client()
        response = client.list_skill_access_control(skillName=skill_name)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def update_skill_access_control(
    skill_name: str,
    skill_user_account_id: str,
    access_status: str,
) -> str:
    """Enable or disable access for an AWS account to a skill."""
    try:
        client = registry_client()
        response = client.update_skill_access_control(
            skillName=skill_name,
            skillUserAccountId=skill_user_account_id,
            accessStatus=access_status,
            idempotencyToken=str(uuid.uuid4()),
        )
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
