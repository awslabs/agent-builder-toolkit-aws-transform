# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import base64
import json
from unittest import mock

import pytest
from agent_builder_agentic_mcp.custom_types.hitl.auto_form import (
    AutoFormHitlTaskArguments,
    AutoFormHitlTaskProperties,
    FieldType,
    FileUploadField,
    InfoContainerField,
    JsonBlockField,
    LabelValueItem,
    MultiselectField,
    RadioGroupField,
    RadioOption,
    SelectField,
    SelectOption,
    TextField,
)
from agent_builder_agentic_mcp.custom_types.hitl.table import (
    ColumnDefinition,
    TableComponentHitlInputParams,
    TableComponentProperties,
    TableItem,
)
from agent_builder_agentic_mcp.datamodels import (
    ArtifactReference,
    ArtifactType,
    CategoryType,
    FileType,
)
from agent_builder_agentic_mcp.server._advanced_tools import (
    create_autoform_hitl_task,
    create_autotable_hitl_task,
    create_hitl_task_with_json_input,
    create_s3_connector_hitl_task,
    download_artifact_to_string,
    retrieve_hitl_output_as_string,
    upload_artifact_from_string,
)


class TestDownloadArtifactToString:
    """Test cases for download_artifact_to_string function."""

    @pytest.mark.anyio
    async def test_download_artifact_success(self):
        """Test successful artifact download."""
        # Arrange
        artifact_id = "test-artifact-id"
        visibility = "INTERNAL"
        expected_payload = "test content"

        mock_download_url_resp = {
            "s3preSignedUrl": "https://test-url.com",
            "requestHeaders": {"Authorization": "Bearer token"},
        }

        mock_download_resp = {
            "success": True,
            "filename": "downloaded_file",
            "file_path": "/tmp/path",
            "status": "completed",
        }

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_artifact_download_url"
        ) as mock_create_url, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.download_artifact"
        ) as mock_download, mock.patch(
            "builtins.open", mock.mock_open(read_data=expected_payload)
        ):

            mock_create_url.return_value = mock_download_url_resp
            mock_download.return_value = mock_download_resp

            # Act
            result = await download_artifact_to_string(artifact_id, visibility)

            # Assert
            mock_create_url.assert_called_once_with(artifact_id=artifact_id, visibility=visibility)
            mock_download.assert_called_once()
            assert result["payload"] == expected_payload
            assert "filename" not in result
            assert "file_path" not in result
            assert result["success"] is True

    @pytest.mark.anyio
    async def test_download_artifact_failure(self):
        """Test artifact download failure."""
        # Arrange
        artifact_id = "test-artifact-id"

        mock_download_url_resp = {
            "s3preSignedUrl": "https://test-url.com",
            "requestHeaders": {"Authorization": "Bearer token"},
        }

        mock_download_resp = {"success": False, "error": "Download failed"}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_artifact_download_url"
        ) as mock_create_url, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.download_artifact"
        ) as mock_download:

            mock_create_url.return_value = mock_download_url_resp
            mock_download.return_value = mock_download_resp

            # Act & Assert
            with pytest.raises(Exception, match="Failed to download artifact"):
                await download_artifact_to_string(artifact_id)


class TestUploadArtifactFromString:
    """Test cases for upload_artifact_from_string function."""

    @pytest.mark.anyio
    async def test_upload_artifact_success(self):
        """Test successful artifact upload."""
        # Arrange
        payload = "test content"
        artifact_reference = ArtifactReference(
            artifact_type=ArtifactType(
                category_type=CategoryType.HITL_FROM_AGENT, file_type=FileType.JSON
            )
        )

        mock_upload_url_resp = {
            "s3preSignedUrl": "https://test-url.com",
            "requestHeaders": {"Authorization": "Bearer token"},
            "artifactId": "test-artifact-id",
        }

        mock_upload_resp = {
            "success": True,
            "artifact_id": "test-artifact-id",
            "headers_used": {"Content-Type": "application/json"},
        }

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_artifact_upload_url"
        ) as mock_create_url, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.upload_artifact"
        ) as mock_upload, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.complete_artifact_upload"
        ) as mock_complete:

            mock_create_url.return_value = mock_upload_url_resp
            mock_upload.return_value = mock_upload_resp
            mock_complete.return_value = {"status": "completed"}

            # Act
            result = await upload_artifact_from_string(payload, artifact_reference)

            # Assert
            mock_create_url.assert_called_once()
            mock_upload.assert_called_once()
            mock_complete.assert_called_once_with(artifact_id="test-artifact-id")
            assert result["success"] is True
            assert "headers_used" not in result

    @pytest.mark.anyio
    async def test_upload_artifact_failure(self):
        """Test artifact upload failure."""
        # Arrange
        payload = "test content"
        artifact_reference = ArtifactReference(
            artifact_type=ArtifactType(
                category_type=CategoryType.HITL_FROM_AGENT, file_type=FileType.JSON
            )
        )

        mock_upload_url_resp = {
            "s3preSignedUrl": "https://test-url.com",
            "requestHeaders": {"Authorization": "Bearer token"},
            "artifactId": "test-artifact-id",
        }

        mock_upload_resp = {"success": False, "error": "Upload failed"}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_artifact_upload_url"
        ) as mock_create_url, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.upload_artifact"
        ) as mock_upload, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.logger"
        ):

            mock_create_url.return_value = mock_upload_url_resp
            mock_upload.return_value = mock_upload_resp

            # Act & Assert
            with pytest.raises(Exception, match="Failed to upload artifact"):
                await upload_artifact_from_string(payload, artifact_reference)

    @pytest.mark.anyio
    async def test_upload_artifact_exception_handling(self):
        """Test exception handling in upload_artifact_from_string."""
        # Arrange
        payload = "test content"
        artifact_reference = ArtifactReference(
            artifact_type=ArtifactType(
                category_type=CategoryType.HITL_FROM_AGENT, file_type=FileType.JSON
            )
        )

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_artifact_upload_url"
        ) as mock_create_url, mock.patch("agent_builder_agentic_mcp.server._advanced_tools.logger"):
            mock_create_url.side_effect = Exception("Network error")

            # Act & Assert
            with pytest.raises(Exception, match="Network error"):
                await upload_artifact_from_string(payload, artifact_reference)


class TestCreateHitlTaskWithJsonInput:
    """Test cases for create_hitl_task_with_json_input function."""

    @pytest.mark.anyio
    async def test_create_hitl_task_success(self):
        """Test successful HITL task creation."""
        # Arrange
        ux_component_id = "TestComponent"
        description = "Test description"
        title = "Test title"
        step_id = "test-step-id"
        json_input = {"test": "data"}

        mock_upload_resp = {"artifact_id": "test-artifact-id", "success": True}
        mock_create_resp = {"hitl_task_id": "test-hitl-id", "status": "created"}
        mock_start_resp = {"status": "started", "active": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.upload_artifact_from_string"
        ) as mock_upload, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task"
        ) as mock_create, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.start_hitl_task"
        ) as mock_start:

            mock_upload.return_value = mock_upload_resp
            mock_create.return_value = mock_create_resp
            mock_start.return_value = mock_start_resp

            # Act
            result = await create_hitl_task_with_json_input(
                ux_component_id=ux_component_id,
                description=description,
                title=title,
                step_id=step_id,
                json_input=json_input,
            )

            # Assert
            mock_upload.assert_called_once()
            mock_create.assert_called_once()
            mock_start.assert_called_once()

            # Verify merged response
            assert result["artifact_id"] == "test-artifact-id"
            assert result["hitl_task_id"] == "test-hitl-id"
            assert result["status"] == "started"
            assert result["active"] is True

    @pytest.mark.anyio
    async def test_create_hitl_task_with_optional_params(self):
        """Test HITL task creation with optional parameters."""
        # Arrange
        ux_component_id = "TestComponent"
        description = "Test description"
        title = "Test title"
        step_id = "test-step-id"
        json_input = {"test": "data"}
        severity = "HIGH"
        hitl_task_type = "URGENT"
        blocking_type = "BLOCKING"
        expired_at = "2024-12-31T23:59:59Z"
        tag = "test-tag"
        first_in_chain = True

        mock_upload_resp = {"artifact_id": "test-artifact-id"}
        mock_create_resp = {"hitl_task_id": "test-hitl-id"}
        mock_start_resp = {"status": "started"}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.upload_artifact_from_string"
        ) as mock_upload, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task"
        ) as mock_create, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.start_hitl_task"
        ) as mock_start:

            mock_upload.return_value = mock_upload_resp
            mock_create.return_value = mock_create_resp
            mock_start.return_value = mock_start_resp

            # Act
            await create_hitl_task_with_json_input(
                ux_component_id=ux_component_id,
                description=description,
                title=title,
                step_id=step_id,
                json_input=json_input,
                severity=severity,
                hitl_task_type=hitl_task_type,
                blocking_type=blocking_type,
                expired_at=expired_at,
                tag=tag,
                first_in_chain=first_in_chain,
            )

            # Assert
            create_call_args = mock_create.call_args[1]
            assert create_call_args["severity"] == severity
            assert create_call_args["hitl_task_type"] == hitl_task_type
            assert create_call_args["blocking_type"] == blocking_type
            assert create_call_args["expired_at"] == expired_at
            assert create_call_args["tag"] == tag

            start_call_args = mock_start.call_args[1]
            assert start_call_args["first_in_chain"] == first_in_chain


class TestRetrieveHitlOutputAsString:
    """Test cases for retrieve_hitl_output_as_string function."""

    @pytest.mark.anyio
    async def test_retrieve_hitl_output_success(self):
        """Test successful retrieval of HITL output."""
        # Arrange
        hitl_task_id = "test-hitl-id"
        artifact_id = "test-artifact-id"
        expected_payload = "test content"

        mock_hitl_response = {
            "hitl_task": {
                "humanArtifact": {"artifactId": artifact_id},
                "uxComponentId": "TestComponent",
            }
        }

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.get_hitl_task"
        ) as mock_get_hitl, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.download_artifact_to_string"
        ) as mock_download:

            mock_get_hitl.return_value = mock_hitl_response
            mock_download.return_value = {"payload": expected_payload, "success": True}

            # Act
            result = await retrieve_hitl_output_as_string(hitl_task_id)

            # Assert
            mock_get_hitl.assert_called_once_with(hitl_task_id)
            mock_download.assert_called_once_with(artifact_id)
            assert result["payload"] == expected_payload

    @pytest.mark.anyio
    async def test_retrieve_hitl_output_file_upload_component(self):
        """Test retrieval with FileUploadComponent that requires base64 decoding."""
        # Arrange
        hitl_task_id = "test-hitl-id"
        artifact_id = "test-artifact-id"
        test_content = "decoded content"
        encoded_content = base64.b64encode(test_content.encode("utf-8")).decode("utf-8")

        mock_hitl_response = {
            "hitl_task": {
                "humanArtifact": {"artifactId": artifact_id},
                "uxComponentId": "FileUploadComponent",
            }
        }

        mock_payload = {"uploadedFiles": [{"content": encoded_content, "filename": "test.txt"}]}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.get_hitl_task"
        ) as mock_get_hitl, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.download_artifact_to_string"
        ) as mock_download:

            mock_get_hitl.return_value = mock_hitl_response
            mock_download.return_value = {"payload": json.dumps(mock_payload), "success": True}

            # Act
            result = await retrieve_hitl_output_as_string(hitl_task_id)

            # Assert
            assert result["payload"]["uploadedFiles"][0]["content"] == test_content

    @pytest.mark.anyio
    async def test_retrieve_hitl_output_no_artifact(self):
        """Test error when HITL task has no output artifact."""
        # Arrange
        hitl_task_id = "test-hitl-id"
        mock_hitl_response = {
            "hitl_task": {
                "uxComponentId": "TestComponent"
                # Missing humanArtifact
            }
        }

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.get_hitl_task"
        ) as mock_get_hitl:
            mock_get_hitl.return_value = mock_hitl_response

            # Act & Assert
            with pytest.raises(Exception, match="does not have any output artifact"):
                await retrieve_hitl_output_as_string(hitl_task_id)

    @pytest.mark.anyio
    async def test_retrieve_hitl_output_direct_response(self):
        """Test when response is already the hitl_task directly."""
        # Arrange
        hitl_task_id = "test-hitl-id"
        artifact_id = "test-artifact-id"
        expected_payload = "test content"

        mock_hitl_response = {
            "humanArtifact": {"artifactId": artifact_id},
            "uxComponentId": "TestComponent",
        }

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.get_hitl_task"
        ) as mock_get_hitl, mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.download_artifact_to_string"
        ) as mock_download:

            mock_get_hitl.return_value = mock_hitl_response
            mock_download.return_value = {"payload": expected_payload, "success": True}

            # Act
            result = await retrieve_hitl_output_as_string(hitl_task_id)

            # Assert
            assert result["payload"] == expected_payload


class TestCreateS3ConnectorHitlTask:
    """Test cases for create_s3_connector_hitl_task function."""

    @pytest.mark.anyio
    async def test_create_s3_connector_hitl_task_m2(self):
        """Test successful creation of S3 connector HITL task."""
        # Arrange
        step_id = "test-step-id"
        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_s3_connector_hitl_task(step_id)

            # Assert
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["ux_component_id"] == "GeneralConnector"
            assert call_args[1]["step_id"] == step_id
            assert call_args[1]["blocking_type"] == "NON_BLOCKING"
            assert call_args[1]["severity"] == "STANDARD"

            # Verify the JSON input structure
            json_input = call_args[1]["json_input"]
            assert "properties" in json_input
            assert "connector" in json_input["properties"]
            connector = json_input["properties"]["connector"]
            assert connector["connectorType"] == "mainframe_modernization|s3|1"
            assert connector["title"] == "S3 Connector"
            assert len(connector["fields"]) == 2
            assert connector["fields"][0]["fieldName"] == "s3BucketArn"
            assert connector["fields"][1]["fieldName"] == "s3BucketKmsKeyArn"

            assert result == expected_response

    @pytest.mark.anyio
    async def test_create_s3_connector_hitl_task_dotnet(self):
        """Test successful creation of S3 connector HITL task with dotnet type."""
        # Arrange
        step_id = "test-step-id"
        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_s3_connector_hitl_task(step_id, connector_type="dotnet")

            # Assert
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            # Verify the JSON input structure
            json_input = call_args[1]["json_input"]
            connector = json_input["properties"]["connector"]
            assert connector["connectorType"] == "dotnet_modernization|s3|1"
            assert len(connector["fields"]) == 2
            assert connector["fields"][0]["fieldName"] == "s3BucketArn"
            assert connector["fields"][1]["fieldName"] == "s3BucketKmsKeyArn"

            assert result == expected_response


class TestCreateAutoformHitlTask:
    """Test cases for create_autoform_hitl_task function."""

    @pytest.mark.anyio
    async def test_create_autoform_hitl_task_success(self):
        """Test successful creation of autoform HITL task."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Form"
        description = "Test Description"

        # Create test form arguments
        text_field = TextField(
            name="test_field", label="Test Field", type=FieldType.TEXT, required=True
        )

        select_option = SelectOption(label="foo", value="bar")

        select_field = SelectField(
            name="test_select_field",
            label="Test Select Field",
            type=FieldType.SELECT,
            required=True,
            options=[select_option],
        )

        multiselect_field = MultiselectField(
            name="test_multiselect_field",
            label="Test MultiSelect Field",
            type=FieldType.MULTISELECT,
            required=True,
            options=[select_option],
        )

        radiogroup_field = RadioGroupField(
            name="test_radiogroup_field",
            label="Test RadioGroup Field",
            type=FieldType.RADIOGROUP,
            required=True,
            options=[RadioOption(label="foo", value="bar")],
        )

        infocontainer_field = InfoContainerField(
            name="test_infocontainer_field",
            label="Test InfoContainer Field",
            type=FieldType.INFOCONTAINER,
            category="display",
            items=[LabelValueItem(label="hello", value="world")],
        )

        jsonblock_field = JsonBlockField(
            name="test_infocontainer_field",
            label="Test InfoContainer Field",
            type=FieldType.JSONBLOCK,
        )

        fileupload_field = FileUploadField(
            name="test_fileupload_field",
            label="Test FileUpload Field",
            type="fileUploadV2",
            required=True,
        )

        properties = AutoFormHitlTaskProperties(
            title="Form Title",
            description="Form Description",
            fields=[
                text_field,
                select_field,
                multiselect_field,
                radiogroup_field,
                infocontainer_field,
                jsonblock_field,
                fileupload_field,
            ],
        )

        args = AutoFormHitlTaskArguments(properties=properties)
        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_autoform_hitl_task(args, step_id, title, description)

            # Assert
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["ux_component_id"] == "AutoForm"
            assert call_args[1]["step_id"] == step_id
            assert call_args[1]["title"] == title
            assert call_args[1]["description"] == description
            assert call_args[1]["blocking_type"] == "NON_BLOCKING"
            assert call_args[1]["severity"] == "STANDARD"

            # Verify the JSON input contains the form structure
            json_input = call_args[1]["json_input"]
            assert "properties" in json_input
            assert json_input["properties"]["title"] == "Form Title"
            assert len(json_input["properties"]["fields"]) == 7

            text_field = json_input["properties"]["fields"][0]
            assert text_field["type"] == "text"
            assert text_field["variant"] == "text"

            multiselect_field = json_input["properties"]["fields"][2]
            assert multiselect_field["type"] == "multiselect"
            assert multiselect_field["filteringType"] == "none"

            infocontainer_field = json_input["properties"]["fields"][4]
            assert infocontainer_field["type"] == "infocontainer"
            assert infocontainer_field["variant"] == "stacked"

            fileupload_field = json_input["properties"]["fields"][6]
            assert fileupload_field["type"] == "fileUploadV2"
            assert fileupload_field["required"] is True

            assert result == expected_response

    @pytest.mark.anyio
    async def test_create_autoform_hitl_task_with_dict_args(self):
        """Test autoform HITL task creation with dictionary arguments."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Form"
        description = "Test Description"

        args_dict = {
            "properties": {
                "title": "Dict Form Title",
                "fields": [
                    {"name": "dict_field", "label": "Dict Field", "type": "text", "required": False}
                ],
            }
        }

        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_autoform_hitl_task(args_dict, step_id, title, description)

            # Assert
            call_args = mock_create.call_args
            json_input = call_args[1]["json_input"]
            assert json_input["properties"]["title"] == "Dict Form Title"
            assert result == expected_response

    @pytest.mark.anyio
    async def test_create_autoform_hitl_task_blocking_type_validation(self):
        """Test blocking type validation in autoform HITL task."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Form"
        description = "Test Description"

        text_field = TextField(name="test_field", label="Test Field", type=FieldType.TEXT)

        properties = AutoFormHitlTaskProperties(fields=[text_field])
        args = AutoFormHitlTaskArguments(properties=properties)

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = {"success": True}

            # Act - Test BLOCKING type
            await create_autoform_hitl_task(
                args, step_id, title, description, blocking_type="BLOCKING"
            )

            # Assert
            call_args = mock_create.call_args
            assert call_args[1]["blocking_type"] == "BLOCKING"

            # Act - Test invalid type defaults to NON_BLOCKING
            await create_autoform_hitl_task(
                args, step_id, title, description, blocking_type="INVALID"
            )

            # Assert
            call_args = mock_create.call_args
            assert call_args[1]["blocking_type"] == "NON_BLOCKING"


class TestCreateAutotableHitlTask:
    """Test cases for create_autotable_hitl_task function."""

    @pytest.mark.anyio
    async def test_create_autotable_hitl_task_success(self):
        """Test successful creation of autotable HITL task."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Table"
        description = "Test Description"

        # Create test table arguments
        column_def = ColumnDefinition(header="Test Column", field="test_field", type="text")

        table_item = TableItem(id="item1")

        properties = TableComponentProperties(
            columnDefinitions=[column_def], items=[table_item], header="Test Table Header"
        )

        args = TableComponentHitlInputParams(properties=properties)
        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_autotable_hitl_task(args, step_id, title, description)

            # Assert
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["ux_component_id"] == "TableComponent"
            assert call_args[1]["step_id"] == step_id
            assert call_args[1]["title"] == title
            assert call_args[1]["description"] == description
            assert call_args[1]["blocking_type"] == "NON_BLOCKING"
            assert call_args[1]["severity"] == "STANDARD"

            # Verify the JSON input contains the table structure
            json_input = call_args[1]["json_input"]
            assert "properties" in json_input
            assert json_input["properties"]["header"] == "Test Table Header"
            assert len(json_input["properties"]["columnDefinitions"]) == 1
            assert len(json_input["properties"]["items"]) == 1

            assert result == expected_response

    @pytest.mark.anyio
    async def test_create_autotable_hitl_task_with_dict_args(self):
        """Test autotable HITL task creation with dictionary arguments."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Table"
        description = "Test Description"

        args_dict = {
            "properties": {
                "header": "Dict Table Header",
                "columnDefinitions": [
                    {"header": "Dict Column", "field": "dict_field", "type": "text"}
                ],
                "items": [{"id": "dict_item1"}],
            }
        }

        expected_response = {"hitl_task_id": "test-hitl-id", "success": True}

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = expected_response

            # Act
            result = await create_autotable_hitl_task(args_dict, step_id, title, description)

            # Assert
            call_args = mock_create.call_args
            json_input = call_args[1]["json_input"]
            assert json_input["properties"]["header"] == "Dict Table Header"
            assert result == expected_response

    @pytest.mark.anyio
    async def test_create_autotable_hitl_task_blocking_type_validation(self):
        """Test blocking type validation in autotable HITL task."""
        # Arrange
        step_id = "test-step-id"
        title = "Test Table"
        description = "Test Description"

        column_def = ColumnDefinition(header="Test Column", field="test_field")
        table_item = TableItem(id="item1")
        properties = TableComponentProperties(
            columnDefinitions=[column_def], items=[table_item], header="Test Header"
        )
        args = TableComponentHitlInputParams(properties=properties)

        with mock.patch(
            "agent_builder_agentic_mcp.server._advanced_tools.create_hitl_task_with_json_input"
        ) as mock_create:
            mock_create.return_value = {"success": True}

            # Act - Test BLOCKING type
            await create_autotable_hitl_task(
                args, step_id, title, description, blocking_type="BLOCKING"
            )

            # Assert
            call_args = mock_create.call_args
            assert call_args[1]["blocking_type"] == "BLOCKING"

            # Act - Test invalid type defaults to NON_BLOCKING
            await create_autotable_hitl_task(
                args, step_id, title, description, blocking_type="INVALID"
            )

            # Assert
            call_args = mock_create.call_args
            assert call_args[1]["blocking_type"] == "NON_BLOCKING"
