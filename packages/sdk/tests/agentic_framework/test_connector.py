# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import threading
from datetime import datetime, timezone
from unittest import mock

import pytest

from agent_builder_sdk.agentic_framework.connector import Connector
from agent_builder_types.client import TransformAgenticServiceClient


@pytest.fixture(autouse=True)
def retrieve_auth_token():
    with mock.patch(
        "agent_builder_sdk.agentic_framework.agentic_api_helper.retrieve_auth_token"
    ):
        yield


@pytest.fixture
def connector():
    return Connector(
        workspace_id="test-workspace",
        job_id="test-job",
        agent_instance_id="test-agent",
        client=mock.create_autospec(TransformAgenticServiceClient, spec_set=True, instance=True),
    )


@pytest.fixture
def credentials_response():
    return {
        "temporaryCredentials": {
            "awsTemporaryCredentials": {
                "accessKey": "test-access-key",
                "secretKey": "test-secret-key",
                "accessToken": "test-session-token",
                "expirationTime": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        },
        "connectorConfiguration": {"s3BucketArn": "arn:aws:s3:::test-bucket"},
        "targetRegion": "us-east-1",
    }


class TestBuildGeneralConnectorArtifact:
    """Test cases for build_general_connector_artifact method."""

    def test_artifact_has_properties_wrapper(self, connector):
        """The artifact holds the given connector under the top-level "properties" key."""
        fields = [
            {"fieldName": "s3BucketArn", "fieldTitle": "S3 Bucket ARN", "fieldRequired": True},
            {"fieldName": "s3BucketKmsKeyArn", "fieldTitle": "Key ARN", "fieldRequired": False},
        ]

        artifact = connector.build_general_connector_artifact(
            connector_type="platform|s3|1",
            title="Amazon S3",
            description="Connect the S3 bucket",
            fields=fields,
        )

        assert json.loads(artifact) == {
            "properties": {
                "connector": {
                    "connectorType": "platform|s3|1",
                    "title": "Amazon S3",
                    "description": "Connect the S3 bucket",
                    "maxInstances": 1,
                    "fields": fields,
                }
            }
        }


class TestGetConnector:
    """Test cases for get_connector method."""

    def test_get_connector_passes_through(self, connector):
        """The id and the request context go to the client; its response comes back as is."""
        expected_response = {
            "connectorType": "platform|s3|1",
            "configuration": {"s3BucketArn": "arn:aws:s3:::test-bucket"},
            "accountConnection": {"awsAccountConnection": {"status": "ACTIVE"}},
        }
        connector.client.get_connector.return_value = expected_response

        result = connector.get_connector("test-connector")

        assert result == expected_response
        connector.client.get_connector.assert_called_once()
        call_args = connector.client.get_connector.call_args[1]
        assert call_args["connectorId"] == "test-connector"
        assert call_args["requestContext"]["jobMetadata"] == {
            "jobId": "test-job",
            "workspaceId": "test-workspace",
        }
        assert call_args["requestContext"]["agentInstanceId"] == "test-agent"


class TestGetTemporaryCredentialsForConnector:
    """Test cases for get_temporary_credentials_for_connector method."""

    def test_target_region_sent_only_when_given(self, connector, credentials_response, caplog):
        """targetRegion is omitted when None and sent when given; the keys are never logged."""
        client_call = connector.client.get_temporary_credentials_for_connector
        client_call.return_value = credentials_response

        with caplog.at_level(logging.INFO):
            result = connector.get_temporary_credentials_for_connector("test-connector")

        assert result == credentials_response["temporaryCredentials"]["awsTemporaryCredentials"]
        assert client_call.call_args[1]["connectorId"] == "test-connector"
        assert client_call.call_args[1]["requestContext"]["agentInstanceId"] == "test-agent"
        assert "targetRegion" not in client_call.call_args[1]
        assert "test-connector" in caplog.text
        for secret in ("test-access-key", "test-secret-key", "test-session-token"):
            assert secret not in caplog.text

        connector.get_temporary_credentials_for_connector("test-connector", "us-west-2")

        assert client_call.call_args[1]["targetRegion"] == "us-west-2"

    @pytest.mark.parametrize(
        "root_level, botocore_level, level_in_call",
        [
            (logging.DEBUG, logging.NOTSET, logging.INFO),
            (logging.WARNING, logging.DEBUG, logging.INFO),
            (logging.WARNING, logging.NOTSET, logging.WARNING),
        ],
        ids=["root at DEBUG", "botocore at DEBUG", "root at WARNING"],
    )
    def test_botocore_does_not_log_the_response_body(
        self, connector, credentials_response, caplog, root_level, botocore_level, level_in_call
    ):
        """botocore is held at INFO or above for the call, then gets its earlier level back."""
        caplog.set_level(root_level)
        caplog.set_level(botocore_level, logger="botocore")
        botocore_logger = logging.getLogger("botocore")
        parser_logger = logging.getLogger("botocore.parsers")
        client_call = connector.client.get_temporary_credentials_for_connector
        levels_in_call = []

        def respond(**kwargs):
            levels_in_call.append(parser_logger.getEffectiveLevel())
            parser_logger.debug("Response body: %r", credentials_response)
            return credentials_response

        client_call.side_effect = respond

        result = connector.get_temporary_credentials_for_connector("test-connector")

        assert result["secretKey"] == "test-secret-key"
        assert "test-secret-key" not in caplog.text
        assert levels_in_call == [level_in_call]
        assert botocore_logger.level == botocore_level

        client_call.side_effect = RuntimeError("no response")
        with pytest.raises(RuntimeError):
            connector.get_temporary_credentials_for_connector("test-connector")

        assert botocore_logger.level == botocore_level

    def test_overlapping_calls_do_not_log_the_response_body(
        self, connector, credentials_response, caplog
    ):
        """A call that starts during another one must not bring DEBUG back before it ends."""
        caplog.set_level(logging.DEBUG)
        caplog.set_level(logging.NOTSET, logger="botocore")
        parser_logger = logging.getLogger("botocore.parsers")
        in_call = [threading.Event(), threading.Event()]
        may_return = [threading.Event(), threading.Event()]
        call_numbers = iter(range(2))

        def respond(**kwargs):
            number = next(call_numbers)
            in_call[number].set()
            may_return[number].wait(timeout=5)
            parser_logger.debug("Response body: %r", credentials_response)
            return credentials_response

        connector.client.get_temporary_credentials_for_connector.side_effect = respond
        threads = [
            threading.Thread(
                target=connector.get_temporary_credentials_for_connector, args=("test-connector",)
            )
            for _ in range(2)
        ]

        threads[0].start()
        assert in_call[0].wait(timeout=5)
        threads[1].start()
        # Without the lock the second call is in flight by now; with it, it waits for the first.
        in_call[1].wait(timeout=0.2)
        for thread, event in zip(threads, may_return):
            event.set()
            thread.join(timeout=5)

        assert "test-secret-key" not in caplog.text
        assert logging.getLogger("botocore").level == logging.NOTSET

    @pytest.mark.parametrize(
        "aws_credentials",
        [
            None,
            {"secretKey": "test-secret-key"},
            {"accessKey": "", "secretKey": "test-secret-key"},
            {"accessKey": "test-access-key"},
        ],
        ids=["no credentials", "no access key", "empty access key", "no secret key"],
    )
    def test_missing_credentials_raise(self, connector, aws_credentials):
        """A response without an access key or a secret key raises instead of returning."""
        response = {}
        if aws_credentials is not None:
            response = {"temporaryCredentials": {"awsTemporaryCredentials": aws_credentials}}
        connector.client.get_temporary_credentials_for_connector.return_value = response

        with pytest.raises(ValueError, match="test-connector"):
            connector.get_temporary_credentials_for_connector("test-connector")
