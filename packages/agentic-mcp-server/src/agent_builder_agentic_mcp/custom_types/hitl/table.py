# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EditConfig(BaseModel):
    editing_cell: Optional[bool] = Field(
        default=False, description="Boolean to check if field is editable.", alias="editingCell"
    )
    validation: Optional[str] = Field(default=None, description="Regex for validation.")


class ColumnDefinition(BaseModel):
    header: str = Field(description="The header text for the column")
    field: str = Field(
        description="The field name that corresponds to a property in the table items - used to access and display data for this column"
    )
    type: Optional[Literal["text", "status-indicator", "link"]] = Field(
        default=None,
        description="The column type. 'text' displays plain text values (default behavior). 'status-indicator' expects objects with 'variant' and 'text'. 'link' expects objects with 'href', 'text', and optional 'external', 'variant', 'ariaLabel' properties",
    )
    edit_config: Optional[EditConfig] = Field(
        default=None,
        description="Configuration for inline editing of this column",
        alias="editConfig",
    )


class TableItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Unique identifier for the table item")
    parent_id: Optional[str] = Field(
        default=None,
        description="Optional parent ID for expandable row functionality - must match another item's ID in the same array and cannot reference the same item's ID (no self-referencing)",
        alias="parentId",
    )


class TableComponentProperties(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    column_definitions: List[ColumnDefinition] = Field(
        description="Array of column definitions for the table", alias="columnDefinitions"
    )
    items: List[TableItem] = Field(
        description="Array of data items to display in the table. For status indicator columns, the corresponding field should contain objects with 'variant' and 'text' properties. For link columns, the corresponding field should contain objects with 'href', 'text', and optional 'external', 'variant', 'ariaLabel' properties."
    )
    header: str = Field(description="The header text for the table")
    submit_button: Optional[str] = Field(
        default=None, description="The text for the submit button", alias="submitButton"
    )


class TableComponentHitlInputParams(BaseModel):
    properties: TableComponentProperties = Field(description="The table component HITL properties")
