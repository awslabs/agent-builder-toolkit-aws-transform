# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
import threading
from typing import Callable, TypeVar

import agent_builder_types.type_defs as abt
from agent_builder_sdk.agentic_framework.agentic_api_helper import AgenticApiHelper
from agent_builder_types import TransformAgenticServiceClient

logger = logging.getLogger(__name__)

_BOTOCORE_LOG_LEVEL_LOCK = threading.RLock()
_T = TypeVar("_T")


def _with_quiet_parser_logger(call: Callable[[], _T]) -> _T:
    """Run an API call whose response holds a secret, with `botocore.parsers` at INFO or above.

    At DEBUG, that logger writes the response body. A logger level is process-wide, so the lock
    keeps a concurrent call from restoring DEBUG during this one; at DEBUG it also serializes these
    calls for the network call and retries. The level check takes the lock too: a call that saw
    INFO only because another call raised it would run unguarded once that call restores DEBUG.
    The lock is re-entrant, so a guarded call made inside another one does not block.
    """
    parser_logger = logging.getLogger("botocore.parsers")
    with _BOTOCORE_LOG_LEVEL_LOCK:
        if parser_logger.getEffectiveLevel() < logging.INFO:
            level = parser_logger.level
            parser_logger.setLevel(logging.INFO)
            try:
                return call()
            finally:
                parser_logger.setLevel(level)
    return call()


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

        # At DEBUG, botocore logs requests and responses, and they hold secrets. The SDK's
        # configure_logging() sets DEBUG when STAGE is not prod.
        logging.getLogger("botocore").setLevel(logging.INFO)
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
        context = self._create_request_context()
        return _with_quiet_parser_logger(
            lambda: self.client.get_connector(connectorId=connector_id, requestContext=context)
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

        response = _with_quiet_parser_logger(
            lambda: self.client.get_temporary_credentials_for_connector(**request)
        )

        creds = response.get("temporaryCredentials", {}).get("awsTemporaryCredentials", {})
        # A boto3 client built with keys that are None uses the agent's own role, without an error.
        if not all(creds.get(key) for key in ("accessKey", "secretKey", "accessToken")):
            raise ValueError(f"No temporary credentials returned for connector {connector_id}")

        logger.info(
            f"Retrieved temporary credentials for connector {connector_id} "
            f"(target region: {response.get('targetRegion', target_region)})"
        )
        return creds.copy()
