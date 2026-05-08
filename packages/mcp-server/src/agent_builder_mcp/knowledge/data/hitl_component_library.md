# Component Library Reference

## Overview

This is a comprehensive reference of all CloudScape components available for Dynamic HITL UI. The rendering engine supports 50+ CloudScape components for display. However, only **4 components** have custom wrappers that capture user input via `useFieldInput(fieldId)`: Input, Textarea, RadioGroup, and FileUpload. All other components render visually but do not capture input.

## Critical Rules

1. **All input components MUST have `fieldId`** — Without it, responses get meaningless auto-generated IDs
2. **No submit/cancel/save buttons** — Platform handles submission automatically
3. **Layout components can ONLY contain other components** — Never raw text strings. Wrap text in Box, TextContent, or Header
4. **Use JSON booleans** — `true`/`false`, not `"True"`/`"False"`

## Input Components Quick Reference

### Components that CAPTURE input (have `useFieldInput` wrappers)

| Component | `fieldId` Required | Output Type | Notes |
|-----------|-------------------|-------------|-------|
| Input | Yes | `string` | Single-line text |
| Textarea | Yes | `string` | Multi-line text |
| RadioGroup | Yes | `string` (selected value) | Auto-selects first item if no value |
| FileUpload | Yes | `{ uploadedFiles: [{ content, name, isZip }] }` | Files converted to base64 |

### Components that RENDER but DO NOT capture input (no wrappers -- data silently lost)

| Component | Renders? | Workaround |
|-----------|----------|------------|
| Select | Yes | Use RadioGroup with same options |
| Multiselect | Yes | Multiple RadioGroups, or Textarea |
| Checkbox | Yes | RadioGroup with Yes/No items |
| DatePicker | Yes | Input with placeholder "YYYY-MM-DD" |
| TimeInput | Yes | Input with placeholder "HH:MM" |
| Toggle | Yes | RadioGroup with On/Off items |

**Alternative:** The `AutoForm` UX component (`uxComponentId: "AutoForm"`) has its own field wrappers that DO capture input from select, multiselect, checkbox, and file upload fields. If you need these input types, use AutoForm instead of DynamicHITLRenderEngine.

## Component Categories

1. [Layout Components](#layout-components)
2. [Form Components](#form-components)
3. [Data Display](#data-display)
4. [Feedback Components](#feedback-components)
5. [Navigation Components](#navigation-components)
6. [Charts & Visualizations](#charts--visualizations)
7. [Rich Content](#rich-content)

---

## Layout Components

**WARNING: Layout components can ONLY contain other components in `children`, never raw text strings.**

### Container -- BANNED

**Do not use Container in HITL components.** Container is a page-level component; ESLint rule `no-container-component` rejects it. Use SpaceBetween + Header instead.

### SpaceBetween
Adds consistent spacing between child elements.

**Props:**
- `direction` - "vertical" | "horizontal"
- `size` - "xxxs" | "xxs" | "xs" | "s" | "m" | "l" | "xl" | "xxl"

**Example:**
```json
{
  "type": "SpaceBetween",
  "props": {
    "direction": "vertical",
    "size": "l"
  },
  "children": [
    { "type": "Box", "children": ["Item 1"] },
    { "type": "Box", "children": ["Item 2"] }
  ]
}
```

### ColumnLayout
Creates a responsive column grid.

**Props:**
- `columns` - Number of columns (1-4)
- `variant` - "default" | "text-grid"

**Example:**
```json
{
  "type": "ColumnLayout",
  "props": { "columns": 3 },
  "children": [
    { "type": "Box", "children": ["Column 1"] },
    { "type": "Box", "children": ["Column 2"] },
    { "type": "Box", "children": ["Column 3"] }
  ]
}
```

### Box
Generic container with styling options.

**Props:**
- `padding` - "n" | "xxxs" | "xxs" | "xs" | "s" | "m" | "l" | "xl" | "xxl"
- `margin` - Same as padding
- `textAlign` - "left" | "center" | "right"
- `fontSize` - "body-s" | "body-m" | "heading-xs" | "heading-s" | "heading-m" | "heading-l" | "heading-xl"

**Example:**
```json
{
  "type": "Box",
  "props": {
    "padding": "l",
    "textAlign": "center"
  },
  "children": ["Centered text with padding"]
}
```

### Grid
Advanced grid layout system.

**Props:**
- `gridDefinition` - Array of column definitions

**Example:**
```json
{
  "type": "Grid",
  "props": {
    "gridDefinition": [
      { "colspan": 6 },
      { "colspan": 6 }
    ]
  },
  "children": [
    { "type": "Box", "children": ["Left half"] },
    { "type": "Box", "children": ["Right half"] }
  ]
}
```

---

## Form Components

**WARNING: All input components MUST include a `fieldId` prop.** User responses are returned keyed by `fieldId`.

### Input
Single-line text input.

**Props:**
- `fieldId` (required) - Unique identifier for this input's response
- `type` - "text" | "email" | "tel" | "url" | "password" | "number"
- `placeholder` - Placeholder text
- `disabled` - Boolean
- `readOnly` - Boolean
- `value` - Initial value

**Output:** `string`

**Example:**
```json
{
  "type": "FormField",
  "props": { "label": "Email Address" },
  "children": [
    {
      "type": "Input",
      "props": {
        "fieldId": "userEmail",
        "type": "email",
        "placeholder": "user@example.com"
      }
    }
  ]
}
```

### Textarea
Multi-line text input.

**Props:**
- `fieldId` (required) - Unique identifier
- `placeholder` - Placeholder text
- `rows` - Number of visible rows
- `disabled` - Boolean
- `value` - Initial value

**Output:** `string`

**Example:**
```json
{
  "type": "FormField",
  "props": { "label": "Comments" },
  "children": [
    {
      "type": "Textarea",
      "props": {
        "fieldId": "userComments",
        "placeholder": "Enter description...",
        "rows": 5
      }
    }
  ]
}
```

### Select -- INPUT NOT CAPTURED

**Warning:** Select renders visually but has no `useFieldInput` wrapper. User selections are **silently lost** on submission. Use RadioGroup instead for single selection.

### Checkbox -- INPUT NOT CAPTURED

**Warning:** Checkbox renders visually but has no `useFieldInput` wrapper. Checked state is **silently lost** on submission. Use RadioGroup with Yes/No items instead.

### RadioGroup
Group of radio buttons. Auto-selects the first item if no value is provided.

**Props:**
- `fieldId` (required) - Unique identifier
- `items` - Array of { value, label }
- `value` - Initial selected value

**Output:** `string` (selected value)

**Example:**
```json
{
  "type": "FormField",
  "props": { "label": "Contact Preference" },
  "children": [
    {
      "type": "RadioGroup",
      "props": {
        "fieldId": "contactMethod",
        "items": [
          { "value": "email", "label": "Email" },
          { "value": "phone", "label": "Phone" }
        ]
      }
    }
  ]
}
```

### FileUpload
File upload input. Files are automatically converted to base64.

**Props:**
- `fieldId` (required) - Unique identifier
- `multiple` - Boolean (allow multiple files)
- `accept` - File type filter (e.g., ".js,.json")
- `showFileSize` - Boolean
- `showFileLastModified` - Boolean
- `constraintText` - Help text
- `errorText` - Error message
- `warningText` - Warning message

**Output:**
```json
{ "uploadedFiles": [{ "content": "base64...", "name": "file.js", "isZip": false }] }
```

**Example:**
```json
{
  "type": "FormField",
  "props": { "label": "Upload Files" },
  "children": [
    {
      "type": "FileUpload",
      "props": {
        "fieldId": "configFiles",
        "multiple": true,
        "accept": ".js,.json",
        "constraintText": "Upload JavaScript or JSON files"
      }
    }
  ]
}
```

## Form Components — FormField & Wrappers

### FormField
Wrapper for form inputs with label and validation.

**Props:**
- `label` - Field label
- `description` - Help text
- `constraintText` - Constraint description
- `errorText` - Error message

**Example:**
```json
{
  "type": "FormField",
  "props": {
    "label": "Email Address",
    "constraintText": "Must be a valid email"
  },
  "children": [
    {
      "type": "Input",
      "props": { "fieldId": "email", "type": "email" }
    }
  ]
}
```

## Form Components -- INPUT NOT CAPTURED

The following components render visually but have no `useFieldInput` wrappers. User input is **silently lost** on submission. Use the workarounds listed in the Quick Reference table above.

- **DatePicker** -- Use Input with placeholder "YYYY-MM-DD" instead
- **TimeInput** -- Use Input with placeholder "HH:MM" instead
- **Toggle** -- Use RadioGroup with On/Off items instead
- **Multiselect** -- Use multiple RadioGroups or Textarea instead

---

## Data Display

### Table
Display structured data in rows and columns.

**Props:**
- `header` - Table header text
- `columnDefinitions` - Array of { header, field }
- `items` - Array of data objects

**Example:**
```json
{
  "type": "Table",
  "props": {
    "variant": "borderless",
    "header": "Files",
    "columnDefinitions": [
      { "header": "Name", "field": "name" },
      { "header": "Status", "field": "status" }
    ],
    "items": [
      { "id": "1", "name": "app.js", "status": "Success" },
      { "id": "2", "name": "config.json", "status": "Pending" }
    ]
  }
}
```

**Advanced:** Table cells can contain JSON components:
```json
{
  "items": [
    {
      "id": "1",
      "name": "app.js",
      "status": "{\"type\": \"StatusIndicator\", \"props\": {\"type\": \"success\"}, \"children\": [\"Success\"]}"
    }
  ]
}
```

### Cards
Display items as cards.

**Props:**
- `cardDefinition` - Card layout definition
- `items` - Array of data objects

**Example:**
```json
{
  "type": "Cards",
  "props": {
    "cardDefinition": {
      "header": "name",
      "sections": [
        { "id": "description", "content": "description" }
      ]
    },
    "items": [
      { "name": "Card 1", "description": "Description 1" }
    ]
  }
}
```

### KeyValuePairs
Display key-value pairs.

**Props:**
- `items` - Array of { label, value }
- `columns` - Number of columns

**Example:**
```json
{
  "type": "KeyValuePairs",
  "props": {
    "columns": 2,
    "items": [
      { "label": "Name", "value": "John Doe" },
      { "label": "Email", "value": "john@example.com" }
    ]
  }
}
```

### StatusIndicator
Display status with icon and color.

**Props:**
- `type` - "success" | "error" | "warning" | "info" | "stopped" | "pending" | "in-progress" | "loading"

**Example:**
```json
{
  "type": "StatusIndicator",
  "props": { "type": "success" },
  "children": ["Completed"]
}
```

---

## Feedback Components

### Alert
Display important messages.

**Props:**
- `type` - "success" | "error" | "warning" | "info"
- `header` - Alert header
- `dismissible` - Boolean

**Example:**
```json
{
  "type": "Alert",
  "props": {
    "type": "info",
    "header": "Important Notice"
  },
  "children": ["Please review the information below."]
}
```

### Flashbar
Display multiple notifications.

**Props:**
- `items` - Array of notification objects

**Example:**
```json
{
  "type": "Flashbar",
  "props": {
    "items": [
      {
        "type": "success",
        "content": "File uploaded successfully"
      }
    ]
  }
}
```

### ProgressBar
Show progress indicator.

**Props:**
- `value` - Progress value (0-100)
- `status` - "in-progress" | "success" | "error"
- `label` - Progress label

**Example:**
```json
{
  "type": "ProgressBar",
  "props": {
    "value": 75,
    "status": "in-progress",
    "label": "Uploading files"
  }
}
```

### Spinner
Loading indicator.

**Props:**
- `size` - "normal" | "big" | "large"

**Example:**
```json
{
  "type": "Spinner",
  "props": { "size": "large" }
}
```

---

## Navigation Components

### Button
Clickable button.

**Props:**
- `variant` - "primary" | "normal" | "link" | "inline-link" | "icon"
- `iconName` - Icon name
- `iconAlign` - "left" | "right"
- `href` - URL for link buttons
- `target` - "_blank" for new tab

**Example:**
```json
{
  "type": "Button",
  "props": {
    "variant": "primary",
    "iconName": "add-plus"
  },
  "children": ["Add Item"]
}
```

### ButtonDropdown
Dropdown menu triggered by a button.

**Props:**
- `items` - Array of { id, text, href?, disabled? }
- `variant` - "primary" | "normal" | "icon"

**Example:**
```json
{
  "type": "ButtonDropdown",
  "props": {
    "items": [
      { "id": "edit", "text": "Edit" },
      { "id": "delete", "text": "Delete" }
    ]
  },
  "children": ["Actions"]
}
```

### ButtonGroup
Group of related buttons displayed together.

**Props:**
- `variant` - "icon"
- `items` - Array of button definitions

**Example:**
```json
{
  "type": "ButtonGroup",
  "props": {
    "variant": "icon",
    "items": [
      { "type": "icon-button", "id": "copy", "iconName": "copy", "text": "Copy" },
      { "type": "icon-button", "id": "delete", "iconName": "remove", "text": "Delete" }
    ]
  }
}
```

### ToggleButton
A button that toggles between pressed and unpressed states.

**Props:**
- `pressed` - Boolean
- `iconName` - Icon name

**Example:**
```json
{
  "type": "ToggleButton",
  "props": { "pressed": false, "iconName": "star" },
  "children": ["Favorite"]
}
```

### CopyToClipboard
Button that copies text to clipboard.

**Props:**
- `copyButtonText` - Button label
- `copySuccessText` - Text shown after copy
- `textToCopy` - The text to copy

**Example:**
```json
{
  "type": "CopyToClipboard",
  "props": {
    "copyButtonText": "Copy ARN",
    "copySuccessText": "Copied!",
    "textToCopy": "arn:aws:s3:::my-bucket"
  }
}
```

### Link
Hyperlink.

**Props:**
- `href` - URL
- `external` - Boolean (opens in new tab)
- `variant` - "primary" | "secondary"

**Example:**
```json
{
  "type": "Link",
  "props": {
    "href": "https://example.com",
    "external": true
  },
  "children": ["Learn More"]
}
```

### BreadcrumbGroup
Navigation breadcrumbs.

**Props:**
- `items` - Array of { text, href }

**Example:**
```json
{
  "type": "BreadcrumbGroup",
  "props": {
    "items": [
      { "text": "Home", "href": "/" },
      { "text": "Projects", "href": "/projects" },
      { "text": "Current", "href": "#" }
    ]
  }
}
```

### Tabs
Tabbed navigation.

**Props:**
- `tabs` - Array of { label, id, content }

**Example:**
```json
{
  "type": "Tabs",
  "props": {
    "tabs": [
      {
        "label": "Tab 1",
        "id": "tab1",
        "content": { "type": "Box", "children": ["Content 1"] }
      }
    ]
  }
}
```

---

## Charts & Visualizations

### PieChart
Circular chart for proportional data.

**Props:**
- `data` - Array of { title, value, color }

**Example:**
```json
{
  "type": "PieChart",
  "props": {
    "data": [
      { "title": "Success", "value": 60, "color": "#28a745" },
      { "title": "Pending", "value": 30, "color": "#ffc107" },
      { "title": "Failed", "value": 10, "color": "#dc3545" }
    ]
  }
}
```

### BarChart
Vertical or horizontal bar chart.

**Props:**
- `series` - Array of data series
- `xDomain` - X-axis categories
- `yDomain` - Y-axis range

**Example:**
```json
{
  "type": "BarChart",
  "props": {
    "series": [
      {
        "title": "Files",
        "type": "bar",
        "data": [
          { "x": "Success", "y": 10 },
          { "x": "Failed", "y": 2 }
        ]
      }
    ]
  }
}
```

### LineChart
Line chart for trends over time.

**Props:**
- `series` - Array of data series
- `xDomain` - X-axis values
- `yDomain` - Y-axis range

**Example:**
```json
{
  "type": "LineChart",
  "props": {
    "series": [
      {
        "title": "Progress",
        "type": "line",
        "data": [
          { "x": 1, "y": 10 },
          { "x": 2, "y": 20 },
          { "x": 3, "y": 30 }
        ]
      }
    ]
  }
}
```

### AreaChart
Area chart for cumulative data.

**Props:**
- `series` - Array of data series

**Example:**
```json
{
  "type": "AreaChart",
  "props": {
    "series": [
      {
        "title": "Total",
        "type": "area",
        "data": [
          { "x": 1, "y": 10 },
          { "x": 2, "y": 25 }
        ]
      }
    ]
  }
}
```

---

## Rich Content

### Markdown
Renders rich formatted text with GitHub Flavored Markdown, syntax highlighting, and deeplink support.

**Props:**
- `markdownText` (required) - The markdown content string

**Example:**
```json
{
  "type": "Markdown",
  "props": {
    "markdownText": "## Instructions\n\nPlease review the following:\n\n- Item 1\n- Item 2\n\n```python\nprint('hello')\n```"
  }
}
```

### ContentLoader
Animated skeleton placeholder shown while content is loading. No props needed.

**Example:**
```json
{
  "type": "ContentLoader",
  "props": {}
}
```

---

## Text Components

### Header
Section header.

**Props:**
- `variant` - "h1" | "h2" | "h3"
- `description` - Subtitle text

**Example:**
```json
{
  "type": "Header",
  "props": {
    "variant": "h2",
    "description": "Subtitle text"
  },
  "children": ["Main Title"]
}
```

### TextContent
Formatted text content.

**Props:**
- `variant` - "p" | "small" | "strong" | "code"

**Example:**
```json
{
  "type": "TextContent",
  "props": { "variant": "p" },
  "children": ["Paragraph text"]
}
```

---

## Component Combinations

### Form with Validation
```json
{
  "type": "SpaceBetween",
  "props": { "direction": "vertical", "size": "l" },
  "children": [
    {
      "type": "FormField",
      "props": { "label": "Email" },
      "children": [{ "type": "Input", "props": { "fieldId": "email", "type": "email" } }]
    }
  ]
}
```

Note: No submit button needed — the platform handles submission automatically.

### Table with Status
```json
{
  "type": "Table",
  "props": {
    "columnDefinitions": [
      { "header": "File", "field": "file" },
      { "header": "Status", "field": "status" }
    ],
    "items": [
      {
        "id": "1",
        "file": "app.js",
        "status": "{\"type\": \"StatusIndicator\", \"props\": {\"type\": \"success\"}, \"children\": [\"Done\"]}"
      }
    ]
  }
}
```

---

## Next Steps

- See `common-patterns.md` for complete UI templates
- See `custom-components.md` to add your own components
- Search `keyword_search("HITL validation testing")` to test your JSON

---

## JSON Schema Reference

The authoritative schema is in `TransformUIComponents/schemaRegistry/DynamicHITLRenderEngine.schema.json`.

**Key schema rules:**
- Every component must have a `"type"` field from the allowed enum (~53 CloudScape components + Markdown, ContentLoader)
- Only 4 input components capture data (Input, Textarea, RadioGroup, FileUpload) -- all require `fieldId`
- Table requires `columnDefinitions` and `items` arrays (each item needs `id`) and `variant: "borderless"`
- Markdown requires `markdownText` string prop
- PieChart requires `data` array with `title` (string) and `value` (number)
- Layout components (SpaceBetween, ColumnLayout, Grid, Cards, Tabs, Form) accept only component children, not strings
- Container is BANNED -- use SpaceBetween + Header instead
- Header variant must be one of: h1, h2, h3 (h4-h6 not supported in schema)
- Props go in `"props"` object, never at component root
