# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# flake8: noqa: N815
class FieldType(str, Enum):
    """Enumeration of supported field types."""

    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    RADIOGROUP = "radiogroup"
    MULTISELECT = "multiselect"
    CHECKBOX = "checkbox"
    INFOCONTAINER = "infocontainer"
    JSONBLOCK = "jsonBlock"
    FILEUPLOAD = "fileUploadV2"


class FilteringType(str, Enum):
    """Enumeration of supported filtering type."""

    AUTO = "auto"
    NONE = "none"


class InfoContainerVariantType(str, Enum):
    """Enumeration of supported info container variant type."""

    DEFAULT = "default"
    STACKED = "stacked"


class TextFieldVariantType(str, Enum):
    """Enumeration of supported text field variant type."""

    TEXT = "text"
    NUMBER = "number"


class SelectOption(BaseModel):
    """Configuration for select/multiselect options."""

    label: str = Field(..., description="Display text for the option")
    value: str = Field(..., description="Value returned when option is selected")
    description: Optional[str] = Field(None, description="Description for the option")


class LabelValueItem(BaseModel):
    """Configuration for select/multiselect options."""

    label: str = Field(..., description="The label/key for this item")
    value: str = Field(..., description="The value for this item")


class RadioOption(BaseModel):
    """Configuration for radio button options."""

    label: str = Field(..., description="Display text for the radio option")
    value: str = Field(..., description="Value returned when option is selected")
    description: Optional[str] = Field(None, description="Description for the option")
    disabled: Optional[bool] = Field(False, description="Whether the option is disabled")


class TextValidation(BaseModel):
    """Validation rules for text and textarea fields."""

    pattern: Optional[str] = Field(
        None, description="Regular expression pattern for text field validation"
    )
    minLength: Optional[int] = Field(
        None, alias="minLength", description="Minimum character length for text fields"
    )
    maxLength: Optional[int] = Field(
        None, alias="maxLength", description="Maximum character length for text fields"
    )
    errorMessage: Optional[str] = Field(
        None,
        alias="errorMessage",
        description="Custom error message displayed when validation fails",
    )


class TextField(BaseModel):
    """Text input field configuration."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the input field")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.TEXT]
    required: bool = Field(False, description="Whether the field is required for form submission")
    placeholder: Optional[str] = Field(
        None, description="Placeholder text shown when field is empty"
    )
    validation: Optional[TextValidation] = Field(None, description="Validation rules for the field")
    variant: TextFieldVariantType = Field(
        TextFieldVariantType.TEXT,
        description="Specifies the type of control to render (text, number).",
    )


class TextareaField(BaseModel):
    """Multi-line text input field configuration."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the textarea field")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.TEXTAREA]
    required: bool = Field(False, description="Whether the field is required for form submission")
    placeholder: Optional[str] = Field(
        None, description="Placeholder text shown when field is empty"
    )
    rows: int = Field(3, description="Number of visible text lines for the textarea", ge=1)
    validation: Optional[TextValidation] = Field(None, description="Validation rules for the field")


class SelectField(BaseModel):
    """Select dropdown field configuration."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the select field")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.SELECT]
    required: bool = Field(False, description="Whether the field is required for form submission")
    placeholder: Optional[str] = Field(
        None, description="Placeholder text shown when no option is selected"
    )
    options: List[SelectOption] = Field(
        ..., description="Array of selectable options", min_length=1
    )


class RadioGroupField(BaseModel):
    """Radio group field configuration for single selection."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the radio group")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.RADIOGROUP]
    required: bool = Field(False, description="Whether the field is required for form submission")
    options: List[RadioOption] = Field(
        ..., description="Array of radio button options", min_length=1
    )
    aria_label: Optional[str] = Field(
        None, alias="ariaLabel", description="Accessibility label for screen readers"
    )


class MultiselectField(BaseModel):
    """Multiselect field configuration for multiple option selection."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the multiselect field")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.MULTISELECT]
    required: bool = Field(False, description="Whether the field is required for form submission")
    placeholder: Optional[str] = Field(
        None, description="Placeholder text for the multiselect field"
    )
    options: List[SelectOption] = Field(
        ..., description="Array of selectable options", min_length=1
    )
    filteringType: FilteringType = Field(
        FilteringType.NONE,
        description="Determines how filtering is applied to the list of options. 'auto' enables automatic filtering, 'none' disables filtering.",
    )
    enableSelectAll: bool = Field(
        False,
        description="Enables users to select and deselect all options with a special extra checkbox which is displayed at the start of the dropdown.",
    )


class CheckboxField(BaseModel):
    """Checkbox field configuration for boolean selection."""

    name: str = Field(..., description="Unique identifier for the field")
    label: str = Field(..., description="Display label for the checkbox field")
    description: Optional[str] = Field(
        None, description="Optional description text displayed below the label"
    )
    type: Literal[FieldType.CHECKBOX]
    required: bool = Field(False, description="Whether the field is required")
    default_checked: bool = Field(
        False, alias="defaultChecked", description="Default checked state of the checkbox"
    )


class InfoContainerField(BaseModel):
    """InfoContainer field configuration for displays structured key-value information"""

    name: str = Field(..., description="Unique identifier for the field")
    label: Optional[str] = Field(None, description="Display label for the info container field")
    type: Literal[FieldType.INFOCONTAINER]
    category: Literal["display"]
    header: Optional[str] = Field(None, description="Optional header text for the container")
    variant: InfoContainerVariantType = Field(
        InfoContainerVariantType.STACKED, description="Visual variant of the info container"
    )
    columns: int = Field(
        1, description="Number of columns to display the key-value pairs in", ge=1, le=4
    )
    items: List[LabelValueItem] = Field(
        ..., description="Array of key-value pairs to display", min_length=1
    )


class JsonBlockValidation(BaseModel):
    """Validation configuration for JSON block field"""

    errorMessage: str = Field(
        "Invalid JSON format. Please check your syntax.",
        description="Custom error message to display when JSON is invalid",
    )


class JsonBlockField(BaseModel):
    """JSON input field with validation"""

    name: str = Field(
        ..., description="Internal identifier for the field used for data binding and processing"
    )
    label: str = Field(..., description="The label text displayed for the JSON input field")
    type: Literal[FieldType.JSONBLOCK]
    description: Optional[str] = Field(
        None,
        description="The description text for the JSON field. Provides detailed information about the form field that's displayed below the label.",
    )
    required: bool = Field(False, description="Whether the field is required for form submission")
    placeholder: str = Field(
        "Enter valid JSON...", description="Placeholder text shown when field is empty"
    )
    rows: int = Field(6, description="Number of visible text lines for the JSON textarea", ge=1)
    validation: Optional[JsonBlockValidation] = Field(None, description="Validation configuration")
    initialValue: Optional[str] = Field(
        None, description="Initial JSON value for the field when no data is provided"
    )


class FileUploadValidation(BaseModel):
    """File upload field validation rules"""

    maxFileSize: Optional[int] = Field(
        None, description="Maximum file size in bytes (default: 50MB)", ge=1
    )
    acceptedFileTypes: Optional[List[str]] = Field(
        None,
        description="Array of accepted MIME types (e.g., ['image/jpeg', 'image/png', 'application/pdf']). Empty array allows all types.",
    )
    maxFiles: Optional[int] = Field(
        None, description="Maximum number of files that can be uploaded (default: 1)", ge=1
    )


class FileUploadInitialValue(BaseModel):
    """Initial value for file upload field"""

    artifactId: str = Field(..., description="The artifact ID of the uploaded file")
    name: str = Field(..., description="The name of the file")
    mimeType: str = Field(..., description="The MIME type of the file")


class FileUploadField(BaseModel):
    """File upload field configuration"""

    name: str = Field(
        ..., description="Internal identifier for the field used for data binding and processing"
    )
    label: str = Field(..., description="The label text displayed for the file upload field")
    type: Literal[FieldType.FILEUPLOAD]
    description: Optional[str] = Field(
        None,
        description="The description text for the file upload field. Provides detailed information about the form field that's displayed below the label.",
    )
    required: bool = Field(False, description="Whether the field is required for form submission")
    validation: Optional[FileUploadValidation] = Field(
        None, description="File upload field validation rules"
    )
    initialValue: Optional[List[FileUploadInitialValue]] = Field(
        None, description="Initial file values for the field when data is provided"
    )


class Alert(BaseModel):
    """Alert configuration for form notifications."""

    type: str = Field(..., description="Alert type (info, success, warning, error)")
    message: str = Field(..., description="Alert message content")
    dismissible: bool = Field(True, description="Whether the alert can be dismissed")


class AutoFormHitlTaskProperties(BaseModel):
    """Properties for the Autoform component"""

    title: Optional[str] = Field(None, description="Optional form title displayed at the top")
    description: Optional[str] = Field(
        None, description="Optional form description displayed below the title"
    )
    fields: List[
        Union[
            TextField,
            TextareaField,
            SelectField,
            RadioGroupField,
            MultiselectField,
            CheckboxField,
            InfoContainerField,
            JsonBlockField,
            FileUploadField,
        ]
    ] = Field(
        ..., description="Array of form fields to render in the order they appear", min_length=1
    )
    alerts: Optional[List[Alert]] = Field(
        None, description="Optional alerts to display with the form"
    )


class AutoFormHitlTaskArguments(BaseModel):
    """Configuration for the AutoForm component."""

    properties: AutoFormHitlTaskProperties = Field(
        ..., description="The properties of the AutoForm component"
    )
