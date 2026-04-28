"""Diagnosis tools."""

import json
import time
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..registry._client import registry_client


def register_diagnosis_tools(mcp: FastMCP) -> None:
    """Register diagnosis tools with MCP server."""
    mcp.tool(description="Run a diagnosis for debugging agent issues within a workspace job")(
        run_diagnosis
    )
    mcp.tool(description="Get the status and result of a diagnosis")(get_diagnosis)
    mcp.tool(description="List diagnoses for a workspace job")(list_diagnoses)


def run_diagnosis(
    workspace_id: str,
    job_id: str,
    agent_instance_id: Optional[str] = None,
    question: Optional[str] = None,
) -> str:
    """Run a diagnosis for debugging agent issues within a workspace job."""
    try:
        client = registry_client()
        kwargs = {"workspaceId": workspace_id, "jobId": job_id}
        if agent_instance_id:
            kwargs["agentInstanceId"] = agent_instance_id
        if question:
            kwargs["question"] = question

        create_response = client.create_diagnosis(**kwargs)
        diagnosis_id = create_response["diagnosisId"]

        max_polls = 150
        poll_interval = 2
        for _ in range(max_polls):
            time.sleep(poll_interval)
            get_response = client.get_diagnosis(diagnosisId=diagnosis_id)
            status = get_response.get("status")
            if status in ("COMPLETE", "FAILED"):
                return json.dumps(get_response, indent=2, default=str)

        return json.dumps({"error": f"Diagnosis {diagnosis_id} timed out after 5 minutes"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_diagnosis(diagnosis_id: str) -> str:
    """Get the status and result of a previously created diagnosis."""
    try:
        client = registry_client()
        response = client.get_diagnosis(diagnosisId=diagnosis_id)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_diagnoses(
    workspace_id: str,
    job_id: str,
    max_results: Optional[int] = None,
    next_token: Optional[str] = None,
) -> str:
    """List diagnoses for a workspace job."""
    try:
        client = registry_client()
        kwargs: dict[str, Any] = {"workspaceId": workspace_id, "jobId": job_id}
        if max_results is not None:
            kwargs["maxResults"] = max_results
        if next_token is not None:
            kwargs["nextToken"] = next_token
        response = client.list_diagnoses(**kwargs)
        return json.dumps(response, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
