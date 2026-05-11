# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import re
import typing
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ApiShapeMixin:
    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Converting dataclass to AgenticAPI requests expected format.
        """
        raise NotImplementedError("Perhaps you forgot to implement this method?")


@dataclass(frozen=True)
class AgenticRequestContext(ApiShapeMixin):
    job_id: str
    workspace_id: str
    agent_instance_id: str
    authorization_token: str = field(repr=False)

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        return {
            "jobMetadata": {"jobId": self.job_id, "workspaceId": self.workspace_id},
            "agentInstanceId": self.agent_instance_id,
            "authorizationToken": self.authorization_token,
        }


def is_valid_checksum(hash_string: str) -> bool:
    """
    Check if the string matches the required SHA-256 checksum format.

    According to the API model, the SHA-256 checksum must:
    - Be between 1 and 64 characters in length
    - Match the base64 pattern: ^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$

    Args:
        hash_string: The string to validate as a SHA-256 checksum

    Returns:
        bool: True if the string is a valid SHA-256 checksum format, False otherwise
    """
    # Check length constraint
    if not (1 <= len(hash_string) <= 64):
        return False

    # Check base64 pattern
    pattern = r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$"
    return bool(re.match(pattern, hash_string))


class FileType(str, Enum):
    """
    Defines the structural and content characteristics of data.
    """

    ZIP = "ZIP"
    JSON = "JSON"
    PDF = "PDF"
    HTML = "HTML"
    TXT = "TXT"
    MARKDOWN = "MARKDOWN"
    CSV = "CSV"
    PPTX = "PPTX"
    XLSX = "XLSX"


class CategoryType(str, Enum):
    """
    Defines the category of the artifact.
    """

    AGENT_INPUT = "AGENT_INPUT"
    AGENT_OUTPUT = "AGENT_OUTPUT"
    CUSTOMER_INPUT = "CUSTOMER_INPUT"
    CUSTOMER_OUTPUT = "CUSTOMER_OUTPUT"
    HITL_FROM_AGENT = "HITL_FROM_AGENT"
    HITL_FROM_USER = "HITL_FROM_USER"
    INTERNAL = "INTERNAL"
    STATE = "STATE"
    PLAN_STEP_OUTPUT = "PLAN_STEP_OUTPUT"


@dataclass
class ArtifactType(ApiShapeMixin):
    """
    Represents an artifact type with category, file type, and schema type.
    """

    category_type: CategoryType
    file_type: FileType
    schema_type: Optional[str] = None

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "ArtifactType":
        """
        Create an ArtifactType from a dictionary.

        Args:
            data: Dictionary with "categoryType" and "fileType" keys

        Returns:
            ArtifactType instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if "categoryType" not in data:
            raise ValueError("ArtifactType must contain 'categoryType' field")
        if "fileType" not in data:
            raise ValueError("ArtifactType must contain 'fileType' field")

        try:
            category_type = CategoryType(data["categoryType"])
        except ValueError:
            valid_categories = ", ".join([c.value for c in CategoryType])
            raise ValueError(
                f"Invalid categoryType: {data['categoryType']}. Must be one of: {valid_categories}"
            )

        try:
            file_type = FileType(data["fileType"])
        except ValueError:
            valid_file_types = ", ".join([f.value for f in FileType])
            raise ValueError(
                f"Invalid fileType: {data['fileType']}. Must be one of: {valid_file_types}"
            )

        schema_type = data.get("schemaType")

        return cls(
            category_type=category_type,
            file_type=file_type,
            schema_type=schema_type,
        )

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Convert to dictionary format for API requests.

        Returns:
            Dictionary with "categoryType", "fileType", and optionally "schemaType" keys
        """
        result = {
            "categoryType": self.category_type.value,
            "fileType": self.file_type.value,
        }
        if self.schema_type is not None:
            result["schemaType"] = self.schema_type
        return result


@dataclass
class FileMetadata(ApiShapeMixin):
    """
    Represents the file metadata with a path and description.
    """

    path: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "FileMetadata":
        """
        Create a FileMetadata object from a dictionary.

        Args:
            data: Dictionary with "path" and "description" keys

        Returns:
            FileMetadata instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if "path" not in data:
            raise ValueError("FileMetadata must contain 'path' field")

        path = data.get("path")
        description = data.get("description")

        return cls(
            path=path,
            description=description,
        )

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Convert to dictionary format for API requests.

        Returns:
            Dictionary with "path" and optionally "description" keys
        """
        result = {
            "path": self.path,
        }
        if self.description is not None:
            result["description"] = self.description
        return result


@dataclass
class MetadataContext(ApiShapeMixin):
    """
    Represents metadata context with schema version and content.
    """

    schema_version: Optional[str] = None
    content: Optional[typing.Dict[str, typing.Any]] = None

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "MetadataContext":
        """
        Create a MetadataContext from a dictionary.

        Args:
            data: Dictionary with optional "schemaVersion" and "content" keys

        Returns:
            MetadataContext instance
        """
        return cls(schema_version=data.get("schemaVersion"), content=data.get("content"))

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Convert to dictionary format for serialization.

        Returns:
            Dictionary with "schemaVersion" and "content" keys (only if not None)
        """
        result: typing.Dict[str, typing.Any] = {}
        if self.schema_version is not None:
            result["schemaVersion"] = self.schema_version
        if self.content is not None:
            result["content"] = self.content
        return result


@dataclass
class ArtifactReference(ApiShapeMixin):
    """
    Represents a reference to an artifact, either by type or ID.
    """

    artifact_type: Optional[ArtifactType] = None
    artifact_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.artifact_type is None and self.artifact_id is None:
            raise ValueError("Either artifactType or artifactId must be provided")
        if self.artifact_type is not None and self.artifact_id is not None:
            raise ValueError("Only one of artifactType or artifactId can be provided")

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> "ArtifactReference":
        """
        Create an ArtifactReference from a dictionary.

        Args:
            data: Dictionary with either "artifactType" or "artifactId" key

        Returns:
            ArtifactReference instance

        Raises:
            ValueError: If neither or both fields are provided
        """
        has_artifact_type = "artifactType" in data
        has_artifact_id = "artifactId" in data

        if not has_artifact_type and not has_artifact_id:
            raise ValueError("ArtifactReference must contain either 'artifactType' or 'artifactId'")
        if has_artifact_type and has_artifact_id:
            raise ValueError(
                "ArtifactReference must contain only one of 'artifactType' or 'artifactId'"
            )

        if has_artifact_type:
            artifact_type = ArtifactType.from_dict(data["artifactType"])
            return cls(artifact_type=artifact_type)
        else:
            return cls(artifact_id=data["artifactId"])

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Convert to dictionary format for API requests.

        Returns:
            Dictionary with either "artifactType" or "artifactId" key
        """
        if self.artifact_type is not None:
            return {"artifactType": self.artifact_type.to_dict()}
        else:
            return {"artifactId": self.artifact_id}
