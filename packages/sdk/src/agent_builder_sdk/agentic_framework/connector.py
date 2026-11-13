# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import threading

import agent_builder_types.type_defs as abt
from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_types import TransformAgenticServiceClient

logger = logging.getLogger(__name__)

_BOTOCORE_LOG_LEVEL_LOCK = threading.Lock()


class Connector(AgenticApiHelper):
    """Gives an agent temporary AWS credentials for a customer resource through an AWS Transform
    connector.

    To read files in a customer's S3 bucket, use the platform S3 connector, type `platform|s3|1`.
    It works for every agent. The MCP tool `create_platform_connector_hitl_task` asks the user for
    it. Workload-owned connector types work only for allowlisted agents; other agents get
    "not authorized to access this type of connector".

    Example, in a custom tool that gets the connector id from the model:

        import boto3
        from agent_builder_sdk.agentic_framework.client_factory import create_agentic_api_client
        from agent_builder_sdk.agentic_framework.connector import Connector
        from agent_builder_sdk.env_var import get_agent_context_from_env

        ctx = get_agent_context_from_env()
        connector = Connector(
            workspace_id=ctx.workspace_id,
            job_id=ctx.job_id,
            agent_instance_id=ctx.agent_instance_id,
            client=create_agentic_api_client(),
        )
        info = connector.get_connector(connector_id)
        if info["accountConnection"]["awsAccountConnection"]["status"] != "ACTIVE":
            ...  # tell the user the connector still waits for approval
        bucket = info["configuration"]["s3BucketArn"].split(":::")[-1]
        creds = connector.get_temporary_credentials_for_connector(connector_id)
        s3 = boto3.client(
            "s3",
            aws_access_key_id=creds["accessKey"],
            aws_secret_access_key=creds["secretKey"],
            aws_session_token=creds["accessToken"],
        )

    The credentials are secrets: never return them to the model.
    """

    client: TransformAgenticServiceClient

    def build_general_connector_artifact(
        self,
        connector_type: str,
        title: str,
        description: str,
        fields: list[dict],
        max_instances: int = 1,
    ) -> bytes:
        """Return the input artifact of a GeneralConnector HITL task, as JSON bytes."""
        # The GeneralConnector component reads its input from the top-level "properties" key.
        # Without it the web app cannot render the task.
        payload = {
            "properties": {
                "connector": {
                    "connectorType": connector_type,
                    "title": title,
                    "description": description,
                    "maxInstances": max_instances,
                    "fields": fields,
                }
            }
        }
        return json.dumps(payload).encode("utf-8")

    def get_connector(self, connector_id: str) -> abt.GetConnectorResponseTypeDef:
        """Return the details of a connector.

        The approval status (PENDING, ACTIVE or REJECTED) is at
        `accountConnection.awsAccountConnection.status`. The connector's settings, for example
        `s3BucketArn`, are in `configuration`.
        """
        return self.client.get_connector(
            connectorId=connector_id, requestContext=self._create_request_context()
        )

    def get_temporary_credentials_for_connector(
        self, connector_id: str, target_region: str | None = None
    ) -> abt.AwsTemporaryCredentialsTypeDef:
        """Return temporary AWS credentials for the connector's resource.

        The result has the keys `accessKey`, `secretKey`, `accessToken` (the session token) and
        `expirationTime` (a timezone-aware datetime). The credentials are valid for about one
        hour; call again after that.

        Raises:
            ValueError: The response holds no access key or no secret key.
        """
        request: dict = {
            "connectorId": connector_id,
            "requestContext": self._create_request_context(),
        }
        if target_region is not None:
            request["targetRegion"] = target_region

        botocore_logger = logging.getLogger("botocore")
        # At DEBUG, botocore logs the response body, which holds the keys. A logger level is
        # process-wide, so without the lock a concurrent call restores DEBUG during this one.
        with _BOTOCORE_LOG_LEVEL_LOCK:
            level = botocore_logger.level
            botocore_logger.setLevel(max(botocore_logger.getEffectiveLevel(), logging.INFO))
            try:
                response = self.client.get_temporary_credentials_for_connector(**request)
            finally:
                botocore_logger.setLevel(level)

        creds = response.get("temporaryCredentials", {}).get("awsTemporaryCredentials", {})
        # A boto3 client built with keys that are None uses the agent's own role, without an error.
        if not creds.get("accessKey") or not creds.get("secretKey"):
            raise ValueError(f"No temporary credentials returned for connector {connector_id}")

        logger.info(
            f"Retrieved temporary credentials for connector {connector_id} "
            f"(target region: {response.get('targetRegion', target_region)})"
        )
        return creds.copy()
