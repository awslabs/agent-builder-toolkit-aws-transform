# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Advanced MCP Tools - High-Level Convenience Functions

This module contains advanced MCP tools that provide higher-level convenience functions
by combining multiple basic MCP operations.

These tools build upon the basic MCP operations in other modules to provide
streamlined workflows for common use cases.

TODO: enable and add more artifact and connector related tools
"""

import base64
import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Dict, Literal, Optional

from agent_builder_agentic_mcp.custom_types.hitl.auto_form import AutoFormHitlTaskArguments
from agent_builder_agentic_mcp.custom_types.hitl.table import TableComponentHitlInputParams
from agent_builder_agentic_mcp.datamodels import (
    ArtifactReference,
    ArtifactType,
    CategoryType,
    FileType,
)
from agent_builder_agentic_mcp.server import (
    complete_artifact_upload,
    create_artifact_download_url,
    create_artifact_upload_url,
    create_hitl_task,
    download_artifact,
    get_hitl_task,
    mcp,
    start_hitl_task,
    upload_artifact,
)
from agent_builder_agentic_mcp.utils import dig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/atx-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# @mcp.tool()
async def download_artifact_to_string(
    artifact_id: str, visibility: Optional[str] = None
) -> Dict[str, Any]:
    """
    Downloads an artifact from an artifact store into a string

    :param artifact_id: The artifact id of the artifact to download
    :param visibility: The visibility of the artifact
    :return: The downloaded artifact payload and other details
    """
    create_artifact_download_url_resp = await create_artifact_download_url(
        artifact_id=artifact_id, visibility=visibility
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "downloaded_file")
        logger.info(f"Downloading artifact from {artifact_id} to {path}")
        download_artifact_resp = await download_artifact(
            s3_presigned_url=create_artifact_download_url_resp["s3preSignedUrl"],
            request_headers=create_artifact_download_url_resp["requestHeaders"],
            artifact_id=artifact_id,
            output_dir=tmp,
            file_name="downloaded_file",
            is_managed_bucket=create_artifact_download_url_resp.get("artifact", {}).get(
                "storedInAtxBucket", True
            ),
        )
        if not download_artifact_resp["success"]:
            raise Exception(f"Failed to download artifact: {download_artifact_resp}")
        with open(path, "r") as f:
            payload = f.read()
    del download_artifact_resp["filename"]
    del download_artifact_resp["file_path"]
    download_artifact_resp["payload"] = payload
    logger.info(f"Downloaded artifact from {artifact_id} to {path}: {download_artifact_resp}")
    return dict(download_artifact_resp)


@mcp.tool()
async def retrieve_hitl_output_as_string(hitl_task_id: str) -> Dict[str, Any]:
    """
    Retrieves the output of a HITL task as a string

    :param hitl_task_id: The id of the HITL task
    :return: The downloaded output payload and other details about the artifact
    """
    hitl_task_response = await get_hitl_task(hitl_task_id)
    logger.info(f"Retrieving output of HITL task {hitl_task_id}: {hitl_task_response}")

    # Extract the actual hitl_task from the response wrapper
    hitl_task = dig(hitl_task_response, ["hitl_task"])
    if hitl_task is None:
        # Fallback: maybe the response is already the hitl_task directly
        hitl_task = hitl_task_response

    artifact_id = dig(hitl_task, ["humanArtifact", "artifactId"])
    if artifact_id is None:
        raise Exception(f"HITL task id={hitl_task_id} does not have any output artifact")

    logger.info(f"Retrieving artifact: {artifact_id}")

    output = await download_artifact_to_string(artifact_id)

    # Check uxComponentId from the correct hitl_task object
    ux_component_id = dig(hitl_task, ["uxComponentId"])
    if ux_component_id == "FileUploadComponent":
        payload = json.loads(output["payload"])
        for files in payload["uploadedFiles"]:
            encoded_content = files["content"]
            decoded_bytes = base64.b64decode(encoded_content)
            decoded_text = decoded_bytes.decode("utf-8")
            files["content"] = decoded_text
        output["payload"] = payload

    return output


# @mcp.tool()
async def upload_artifact_from_string(
    payload: str,
    artifact_reference: ArtifactReference,
    label: Optional[str] = None,
    plan_step_id: Optional[str] = None,
    visibility: Optional[str] = "INTERNAL",
) -> Dict[str, Any]:
    """
    Creates and uploads to an artifact the provided string payload

    :param payload: The string payload for the artifact
    :param artifact_reference: Configuration about the type of artifact
    :param label: A label for the artifact
    :param plan_step_id: The plan step id associated with the artifact
    :param visibility: The visibility of the artifact
    :return: Details about the uploaded artifact
    """
    logger.info(f"upload_artifact_from_string: {payload}")
    try:
        artifact_upload_resp = await create_artifact_upload_url(
            content_digest=base64.b64encode(
                hashlib.sha256(payload.encode("utf-8")).digest()
            ).decode("utf-8"),
            artifact_reference=artifact_reference.to_dict(),
            label=label,
            plan_step_id=plan_step_id,
            visibility=visibility,
        )

        # Write to a temporary file before upload
        with tempfile.NamedTemporaryFile(mode="w") as tmpfile:
            tmpfile.write(payload)
            tmpfile.seek(0)
            upload_artifact_resp = await upload_artifact(
                s3_presigned_url=artifact_upload_resp["s3preSignedUrl"],
                request_headers=artifact_upload_resp["requestHeaders"],
                artifact_id=artifact_upload_resp["artifactId"],
                file_path=tmpfile.name,
            )

        if not upload_artifact_resp.get("success"):
            raise Exception(f"Failed to upload artifact: {upload_artifact_resp}")

        await complete_artifact_upload(artifact_id=artifact_upload_resp["artifactId"])

        del upload_artifact_resp["headers_used"]
        return dict(upload_artifact_resp)
    except Exception as ex:
        logger.error("Failed to upload artifact", ex)
        raise ex


# @mcp.tool()
async def create_hitl_task_with_json_input(
    ux_component_id: str,
    description: str,
    title: str,
    step_id: str,
    json_input: Dict[str, Any],
    severity: Optional[str] = "STANDARD",
    hitl_task_type: Optional[str] = "NORMAL",
    blocking_type: Literal["BLOCKING", "NON_BLOCKING"] = "BLOCKING",
    expired_at: Optional[str] = None,
    tag: Optional[str] = None,
    first_in_chain: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Creates a HITL task with the specified json input by creating an artifact and uploading the json input, then using
    the artifact id to start the HITL task, and finally starting the HITL.

    :param ux_component_id: The UX component identifier for the HITL task
    :param description: The description for the HITL task
    :param title: The title for the HITL task
    :param step_id: The step id for the step associated with the HITL task. This must be a valid step in the current job plan.
    :param json_input: The JSON payload to supply as input to the HITL task
    :param severity: The severity of the HITL
    :param hitl_task_type: The task type of the HITL
    :param blocking_type: The blocking type for the HITL task
    :param expired_at: The time at which the HITL expires
    :param tag: A tag for the HITL
    :param first_in_chain: Optional flag indicating if this is the first task in a chain
    :return: Details about the created HITL
    """
    logger.info(f"create_hitl_task_with_json_input: {json_input}")
    upload_resp = await upload_artifact_from_string(
        payload=json.dumps(json_input),
        artifact_reference=ArtifactReference(
            artifact_type=ArtifactType(
                category_type=CategoryType.HITL_FROM_AGENT, file_type=FileType.JSON
            ),
        ),
        plan_step_id=step_id,
        visibility="INTERNAL",
    )

    create_hitl_resp = await create_hitl_task(
        ux_component_id=ux_component_id,
        description=description,
        title=title,
        severity=severity,
        hitl_task_type=hitl_task_type,
        step_id=step_id,
        blocking_type=blocking_type,
        hitl_request_artifact={"artifactId": upload_resp["artifact_id"]},
        expired_at=expired_at,
        tag=tag,
    )

    start_resp = await start_hitl_task(
        hitl_task_id=create_hitl_resp["hitl_task_id"],
        first_in_chain=first_in_chain,
    )

    resp = upload_resp | create_hitl_resp | start_resp
    logger.info(f"create_hitl_task_with_json_input: OUTPUT={resp}")
    return dict(resp)


@mcp.tool()
async def create_s3_connector_hitl_task(
    step_id: str, connector_type: Literal["m2", "dotnet"] = "m2"
) -> Dict[str, Any]:
    """
    Creates a HITL task for a S3 connector and start it. The purpose of this task is to connect to user's s3 bucket

    :param step_id: The step id for the step associated with the HITL task. This must be a valid step in the current job plan.
    :param connector_type: The type of S3 connector to create. Options: "m2" (mainframe_modernization|s3|1) or "dotnet" (dotnet_modernization|s3|1)
    :return: Details about the created HITL task
    """
    connector_type_map = {
        "m2": "mainframe_modernization|s3|1",
        "dotnet": "dotnet_modernization|s3|1",
    }

    json_input = {
        "properties": {
            "connector": {
                "connectorType": connector_type_map[connector_type],
                "title": "S3 Connector",
                "description": "Connect to S3 bucket",
                "maxInstances": 1,
                "fields": [
                    {
                        "fieldName": "s3BucketArn",
                        "fieldTitle": "S3 bucket ARN",
                        "fieldDescription": "",
                        "fieldRequired": True,
                        "fieldInputType": "text",
                        "fieldValidation": "",
                    },
                    {
                        "fieldName": "s3BucketKmsKeyArn",
                        "fieldTitle": "s3 Bucket Encryption Key ARN",
                        "fieldDescription": "",
                        "fieldRequired": True,
                        "fieldInputType": "text",
                        "fieldValidation": "",
                    },
                ],
            }
        }
    }

    return await create_hitl_task_with_json_input(
        ux_component_id="GeneralConnector",
        description="Gather input from the user and create connector",
        title="Configure S3 connector",
        json_input=json_input,
        blocking_type="NON_BLOCKING",
        severity="STANDARD",
        step_id=step_id,
        tag=None,
    )


@mcp.tool()
async def create_autoform_hitl_task(
    args: AutoFormHitlTaskArguments,
    step_id: str,
    title: str,
    description: str,
    blocking_type: Optional[Literal["BLOCKING", "NON_BLOCKING"]] = "NON_BLOCKING",
    severity: Optional[str] = "STANDARD",
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a HITL task for an automatically generated UX form and start it. The purpose of this task is to gather
    data from the user in a structured format. This should be the primary way that details are gathered from the
    user whenever there are many details to gather.

    :param args: The input for the HITL that defines the schema for the form
    :param step_id: The step id for the step associated with the HITL task. This must be a valid step in the current job plan.
    :param title: The title for the HITL task
    :param description: The description for the HITL task
    :param blocking_type: The blocking type of the HITL task
    :param severity: The severity for the HITL task
    :param tag: The tag for the task
    :return: Details about the created HITL task
    """
    json_input = args if isinstance(args, dict) else args.model_dump(exclude_none=True)

    logger.info(f"create_autoform_hitl_task: json_input={json_input}")
    # Ensure blocking_type is a valid literal value
    validated_blocking_type: Literal["BLOCKING", "NON_BLOCKING"] = "NON_BLOCKING"
    if blocking_type == "BLOCKING":
        validated_blocking_type = "BLOCKING"
    elif blocking_type == "NON_BLOCKING":
        validated_blocking_type = "NON_BLOCKING"

    return await create_hitl_task_with_json_input(
        ux_component_id="AutoForm",
        description=description,
        title=title,
        json_input=json_input,
        blocking_type=validated_blocking_type,
        severity=severity,
        step_id=step_id,
        tag=tag,
    )


@mcp.tool()
async def create_autotable_hitl_task(
    args: TableComponentHitlInputParams,
    step_id: str,
    title: str,
    description: str,
    blocking_type: Optional[Literal["BLOCKING", "NON_BLOCKING"]] = "NON_BLOCKING",
    severity: Optional[str] = "STANDARD",
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a HITL task for an automatically generated table component and start it. The purpose of this task is to
    display data to the user in a structured table format with optional editing capabilities.

    :param args: The input for the HITL that defines the schema for the table
    :param step_id: The step id for the step associated with the HITL task. This must be a valid step in the current job plan.
    :param title: The title for the HITL task
    :param description: The description for the HITL task
    :param blocking_type: The blocking type of the HITL task
    :param severity: The severity for the HITL task
    :param tag: The tag for the task
    :return: Details about the created HITL task
    """
    json_input = (
        args if isinstance(args, dict) else args.model_dump(exclude_none=True, by_alias=True)
    )

    logger.info(f"create_autotable_hitl_task: json_input={json_input}")
    # Ensure blocking_type is a valid literal value
    validated_blocking_type: Literal["BLOCKING", "NON_BLOCKING"] = "NON_BLOCKING"
    if blocking_type == "BLOCKING":
        validated_blocking_type = "BLOCKING"
    elif blocking_type == "NON_BLOCKING":
        validated_blocking_type = "NON_BLOCKING"

    return await create_hitl_task_with_json_input(
        ux_component_id="TableComponent",
        description=description,
        title=title,
        json_input=json_input,
        blocking_type=validated_blocking_type,
        severity=severity,
        step_id=step_id,
        tag=tag,
    )
