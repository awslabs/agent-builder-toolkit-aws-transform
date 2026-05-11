# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from agent_builder_agentic_mcp.datamodels import (
    AgenticRequestContext,
    ApiShapeMixin,
    ArtifactReference,
    ArtifactType,
    CategoryType,
    FileType,
    is_valid_checksum,
)


def test_api_shape_mixin_raise_exception_when_used():
    # given
    api_shape_mix = ApiShapeMixin()

    # when / then
    with pytest.raises(NotImplementedError) as exec_info:
        api_shape_mix.to_dict()
        assert str(exec_info.value) == "Perhaps you forgot to implement this method?"


def test_agentic_request_context_hide_auth_token_when_repr():
    # given
    auth_token = "I shall not be seen"
    request_context = AgenticRequestContext(
        job_id="test-job-id",
        workspace_id="test-workspace-id",
        agent_instance_id="agent_instance_id",
        authorization_token=auth_token,
    )

    # when / then
    assert auth_token not in str(f"logging {request_context}")


# Tests for is_valid_checksum function
def test_is_valid_checksum_valid_input():
    # Valid base64 strings of different lengths
    assert is_valid_checksum("AAAA") is True  # 4 chars
    assert (
        is_valid_checksum("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
        is True
    )  # 64 chars
    assert is_valid_checksum("AA==") is True  # With padding


def test_is_valid_checksum_invalid_input():
    # Invalid inputs - too long
    assert is_valid_checksum("A" * 65) is False  # Exceeds 64 char limit
    # Invalid inputs - too short
    assert is_valid_checksum("") is False  # Empty string
    # Invalid inputs - not base64 pattern
    assert is_valid_checksum("ABC!") is False  # Contains invalid character
    assert is_valid_checksum("ABC") is False  # Length not multiple of 4


def test_is_valid_checksum_edge_cases():
    # Edge cases - exactly 64 characters (maximum allowed)
    assert is_valid_checksum("A" * 64) is True
    # Edge cases - exactly 1 character (minimum allowed)
    assert is_valid_checksum("A") is False  # Valid length but invalid base64 (needs padding)
    # Edge cases - with different padding
    assert is_valid_checksum("A===") is False  # Invalid padding
    assert is_valid_checksum("AAA=") is True  # Valid padding


# Tests for FileType enum
def test_file_type_values():
    # Test all enum values
    assert FileType.ZIP.value == "ZIP"
    assert FileType.JSON.value == "JSON"
    assert FileType.PDF.value == "PDF"
    assert FileType.HTML.value == "HTML"
    assert FileType.TXT.value == "TXT"
    assert FileType.MARKDOWN.value == "MARKDOWN"
    assert FileType.CSV.value == "CSV"

    # Test enum creation from string
    assert FileType("ZIP") == FileType.ZIP
    assert FileType("JSON") == FileType.JSON

    # Test invalid enum value
    with pytest.raises(ValueError):
        FileType("INVALID_TYPE")


# Tests for CategoryType enum
def test_category_type_values():
    # Test all enum values
    assert CategoryType.AGENT_INPUT.value == "AGENT_INPUT"
    assert CategoryType.AGENT_OUTPUT.value == "AGENT_OUTPUT"
    assert CategoryType.CUSTOMER_INPUT.value == "CUSTOMER_INPUT"
    assert CategoryType.CUSTOMER_OUTPUT.value == "CUSTOMER_OUTPUT"
    assert CategoryType.HITL_FROM_AGENT.value == "HITL_FROM_AGENT"
    assert CategoryType.HITL_FROM_USER.value == "HITL_FROM_USER"
    assert CategoryType.INTERNAL.value == "INTERNAL"
    assert CategoryType.STATE.value == "STATE"
    assert CategoryType.PLAN_STEP_OUTPUT.value == "PLAN_STEP_OUTPUT"

    # Test enum creation from string
    assert CategoryType("AGENT_INPUT") == CategoryType.AGENT_INPUT
    assert CategoryType("INTERNAL") == CategoryType.INTERNAL

    # Test invalid enum value
    with pytest.raises(ValueError):
        CategoryType("INVALID_CATEGORY")


# Tests for ArtifactType class
def test_artifact_type_creation():
    # Create with required fields only
    artifact_type = ArtifactType(category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON)
    assert artifact_type.category_type == CategoryType.AGENT_OUTPUT
    assert artifact_type.file_type == FileType.JSON
    assert artifact_type.schema_type is None

    # Create with all fields
    artifact_type = ArtifactType(
        category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON, schema_type="test-schema"
    )
    assert artifact_type.category_type == CategoryType.AGENT_OUTPUT
    assert artifact_type.file_type == FileType.JSON
    assert artifact_type.schema_type == "test-schema"


def test_artifact_type_from_dict():
    # Valid dictionary with required fields only
    data = {"categoryType": "AGENT_OUTPUT", "fileType": "JSON"}
    artifact_type = ArtifactType.from_dict(data)
    assert artifact_type.category_type == CategoryType.AGENT_OUTPUT
    assert artifact_type.file_type == FileType.JSON
    assert artifact_type.schema_type is None

    # Valid dictionary with all fields
    data = {"categoryType": "AGENT_OUTPUT", "fileType": "JSON", "schemaType": "test-schema"}
    artifact_type = ArtifactType.from_dict(data)
    assert artifact_type.category_type == CategoryType.AGENT_OUTPUT
    assert artifact_type.file_type == FileType.JSON
    assert artifact_type.schema_type == "test-schema"

    # Missing categoryType
    with pytest.raises(ValueError) as exc_info:
        ArtifactType.from_dict({"fileType": "JSON"})
    assert "must contain 'categoryType' field" in str(exc_info.value)

    # Missing fileType
    with pytest.raises(ValueError) as exc_info:
        ArtifactType.from_dict({"categoryType": "AGENT_OUTPUT"})
    assert "must contain 'fileType' field" in str(exc_info.value)

    # Invalid categoryType
    with pytest.raises(ValueError) as exc_info:
        ArtifactType.from_dict({"categoryType": "INVALID", "fileType": "JSON"})
    assert "Invalid categoryType" in str(exc_info.value)

    # Invalid fileType
    with pytest.raises(ValueError) as exc_info:
        ArtifactType.from_dict({"categoryType": "AGENT_OUTPUT", "fileType": "INVALID"})
    assert "Invalid fileType" in str(exc_info.value)


def test_artifact_type_to_dict():
    # With required fields only
    artifact_type = ArtifactType(category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON)
    artifact_dict = artifact_type.to_dict()
    assert artifact_dict == {"categoryType": "AGENT_OUTPUT", "fileType": "JSON"}

    # With all fields
    artifact_type = ArtifactType(
        category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON, schema_type="test-schema"
    )
    artifact_dict = artifact_type.to_dict()
    assert artifact_dict == {
        "categoryType": "AGENT_OUTPUT",
        "fileType": "JSON",
        "schemaType": "test-schema",
    }


# Tests for ArtifactReference class
def test_artifact_reference_creation():
    # Create with artifact_type
    artifact_type = ArtifactType(category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON)
    artifact_ref = ArtifactReference(artifact_type=artifact_type)
    assert artifact_ref.artifact_type == artifact_type
    assert artifact_ref.artifact_id is None

    # Create with artifact_id
    artifact_ref = ArtifactReference(artifact_id="test-artifact-id")
    assert artifact_ref.artifact_type is None
    assert artifact_ref.artifact_id == "test-artifact-id"

    # Missing both fields
    with pytest.raises(ValueError) as exc_info:
        ArtifactReference()
    assert "Either artifactType or artifactId must be provided" in str(exc_info.value)

    # Both fields provided
    with pytest.raises(ValueError) as exc_info:
        ArtifactReference(artifact_type=artifact_type, artifact_id="test-artifact-id")
    assert "Only one of artifactType or artifactId can be provided" in str(exc_info.value)


def test_artifact_reference_from_dict():
    # Valid dictionary with artifact_type
    data = {"artifactType": {"categoryType": "AGENT_OUTPUT", "fileType": "JSON"}}
    artifact_ref = ArtifactReference.from_dict(data)
    assert artifact_ref.artifact_type is not None
    assert artifact_ref.artifact_type.category_type == CategoryType.AGENT_OUTPUT
    assert artifact_ref.artifact_type.file_type == FileType.JSON
    assert artifact_ref.artifact_id is None

    # Valid dictionary with artifact_id
    data = {"artifactId": "test-artifact-id"}
    artifact_ref = ArtifactReference.from_dict(data)
    assert artifact_ref.artifact_type is None
    assert artifact_ref.artifact_id == "test-artifact-id"

    # Missing both fields
    with pytest.raises(ValueError) as exc_info:
        ArtifactReference.from_dict({})
    assert "must contain either 'artifactType' or 'artifactId'" in str(exc_info.value)

    # Both fields provided
    with pytest.raises(ValueError) as exc_info:
        ArtifactReference.from_dict(
            {
                "artifactType": {"categoryType": "AGENT_OUTPUT", "fileType": "JSON"},
                "artifactId": "test-artifact-id",
            }
        )
    assert "must contain only one of 'artifactType' or 'artifactId'" in str(exc_info.value)

    # Invalid artifactType
    with pytest.raises(ValueError) as exc_info:
        ArtifactReference.from_dict(
            {"artifactType": {"categoryType": "INVALID", "fileType": "JSON"}}
        )
    assert "Invalid categoryType" in str(exc_info.value)


def test_artifact_reference_to_dict():
    # With artifact_type
    artifact_type = ArtifactType(category_type=CategoryType.AGENT_OUTPUT, file_type=FileType.JSON)
    artifact_ref = ArtifactReference(artifact_type=artifact_type)
    artifact_dict = artifact_ref.to_dict()
    assert artifact_dict == {"artifactType": {"categoryType": "AGENT_OUTPUT", "fileType": "JSON"}}

    # With artifact_id
    artifact_ref = ArtifactReference(artifact_id="test-artifact-id")
    artifact_dict = artifact_ref.to_dict()
    assert artifact_dict == {"artifactId": "test-artifact-id"}
