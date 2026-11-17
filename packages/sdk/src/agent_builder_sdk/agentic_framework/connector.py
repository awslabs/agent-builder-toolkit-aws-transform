# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import threading

import agent_builder_types.type_defs as abt
from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_types import TransformAgenticServiceClient

logger = logging.getLogger(__name__)

_BOTOCORE_LOG_LEVEL_LOCK = threading.Lock()


class ConnectorClient(AgenticApiHelper):
    r"""Gives an agent temporary AWS credentials for a customer resource through an AWS Transform
    connector.

    To read files in a customer's S3 bucket, use the platform S3 connector, type `platform|s3|1`.
    It works for every agent. The MCP tool `create_platform_connector_hitl_task` asks the user for
    it. Workload-owned connector types work only for allowlisted agents; other agents get
    "not authorized to access this type of connector".

    Example, in a custom tool that gets the connector id from the model:

        import logging
        import re

        import boto3
        from agent_builder_sdk.agentic_framework.client_factory import create_agentic_api_client
        from agent_builder_sdk.agentic_framework.connector import ConnectorClient
        from agent_builder_sdk.env_var import get_agent_context_from_env

        ctx = get_agent_context_from_env()
        connector_client = ConnectorClient(
            workspace_id=ctx.workspace_id,
            job_id=ctx.job_id,
            agent_instance_id=ctx.agent_instance_id,
            client=create_agentic_api_client(),
        )
        info = connector_client.get_connector(connector_id)
        account = info.get("accountConnection", {}).get("awsAccountConnection", {})
        status = account.get("status", "not connected to an AWS account")
        if status != "ACTIVE":
            raise RuntimeError(f"Connector {connector_id} is {status}: it needs approval first")
        arn = info.get("configuration", {}).get("s3BucketArn", "")
        match = re.fullmatch(r"arn:aws[\w-]*:s3:::([^/]+)", arn)
        if not match:
            raise ValueError(f"Connector {connector_id}: {arn!r} is not an S3 bucket ARN")
        bucket = match.group(1)
        creds = connector_client.get_temporary_credentials_for_connector(connector_id)
        # At DEBUG, botocore logs the access key id and the session token of each request, and
        # the SDK's configure_logging() sets DEBUG when STAGE is not prod.
        logging.getLogger("botocore").setLevel(logging.INFO)
        s3 = boto3.client(
            "s3",
            aws_access_key_id=creds["accessKey"],
            aws_secret_access_key=creds["secretKey"],
            aws_session_token=creds["accessToken"],
        )

    The credentials are secrets: never return them to the model.
    """

    client: TransformAgenticServiceClient

    def get_connector(self, connector_id: str) -> abt.GetConnectorResponseTypeDef:
        """Return the details of a connector.

        The approval status (PENDING, ACTIVE or REJECTED) is at
        `accountConnection.awsAccountConnection.status`. The connector's settings, for example
        `s3BucketArn`, are in `configuration`. Give the model only the fields that the agent needs,
        for example the status and the bucket ARN, never the whole response: the response also
        holds `accountConnection.awsAccountConnection.connectionToken`.
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
            ValueError: The access key, the secret key or the session token is missing or empty.
        """
        request: dict = {
            "connectorId": connector_id,
            "requestContext": self._create_request_context(),
        }
        if target_region is not None:
            request["targetRegion"] = target_region

        parser_logger = logging.getLogger("botocore.parsers")
        # At DEBUG, this logger writes the response body, which holds the keys. A logger level is
        # process-wide, so without the lock a concurrent call restores DEBUG during this one.
        # The lock also serializes credential calls in the process for the network call and retries.
        with _BOTOCORE_LOG_LEVEL_LOCK:
            level = parser_logger.level
            parser_logger.setLevel(max(parser_logger.getEffectiveLevel(), logging.INFO))
            try:
                response = self.client.get_temporary_credentials_for_connector(**request)
            finally:
                parser_logger.setLevel(level)

        creds = response.get("temporaryCredentials", {}).get("awsTemporaryCredentials", {})
        # A boto3 client built with keys that are None uses the agent's own role, without an error.
        if not all(creds.get(key) for key in ("accessKey", "secretKey", "accessToken")):
            raise ValueError(f"No temporary credentials returned for connector {connector_id}")

        logger.info(
            f"Retrieved temporary credentials for connector {connector_id} "
            f"(target region: {response.get('targetRegion', target_region)})"
        )
        return creds.copy()
