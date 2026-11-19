# Component Composition Patterns

## Layout Hierarchy

A2UI uses a flat adjacency list, but the logical hierarchy follows consistent patterns.

### Vertical Stack (most common root)

```json
{
  "id": "root",
  "component": "SpaceBetween",
  "direction": "vertical",
  "size": "l",
  "children": ["section-1", "section-2"]
}
```

Use `size: "l"` between major sections, `size: "m"` between form fields, `size: "s"` for tight groups.

### Multi-Column Layout

```json
{ "id": "metrics-container", "component": "Container", "children": ["metrics-row"] },
{ "id": "metrics-row", "component": "ColumnLayout", "columns": 3, "children": ["col-1", "col-2", "col-3"] }
```

Always place the `ColumnLayout` inside a `Container`; the surrounding layout
must reference `metrics-container`, not `metrics-row`. Each child occupies one
column. Use additional containers inside individual columns only when a column
needs its own visual grouping.

### Metric Card Pattern

Display a key-value metric with styled label and value:

```json
{"id": "metric-card", "component": "Container", "children": ["metric-label", "metric-value"]},
{"id": "metric-label", "component": "Box", "variant": "awsui-key-label", "children": "Total Items"},
{"id": "metric-value", "component": "Box", "variant": "awsui-value-large", "children": {"path": "/data/totalItems"}}
```

For status-colored values, use StatusIndicator instead of Box for the value.

### Grouped Content with Header

```json
{"id": "section", "component": "Container", "header": "Section Title", "children": ["section-content"]},
{"id": "section-content", "component": "SpaceBetween", "direction": "vertical", "size": "m", "children": [...]}
```

Container provides the visual border + header. SpaceBetween inside for even spacing.

### Collapsible Details

```json
{
  "id": "details",
  "component": "ExpandableSection",
  "headerText": "Advanced Options",
  "defaultExpanded": false,
  "children": ["details-content"]
}
```

Use for secondary information that shouldn't dominate the initial view.

### Tabs for Parallel Content

```json
{"id": "tabs", "component": "Tabs", "tabs": [
  {"id": "tab-overview", "label": "Overview", "contentId": "overview-panel"},
  {"id": "tab-details", "label": "Details", "contentId": "details-panel"}
]},
{"id": "overview-panel", "component": "SpaceBetween", "children": [...]},
{"id": "details-panel", "component": "SpaceBetween", "children": [...]}
```

Tab content components exist in the flat array like everything else. `contentId` references them.

### TreeView for Hierarchy

Use `TreeView` when parent-child relationships are the content, such as
application groups, resource ownership, or assessment sections. Items are
nested directly rather than referenced by component ID.

```json
{
  "id": "scope-tree",
  "component": "TreeView",
  "ariaLabel": "Assessment scope",
  "connectorLines": "vertical",
  "items": [
    {
      "id": "production",
      "content": "Production",
      "children": [
        { "id": "checkout", "content": "Checkout service" },
        { "id": "catalog", "content": "Catalog service" }
      ]
    }
  ]
}
```

IDs MUST be unique across the entire tree. Use a bound `expandedItems` array
only when expanded IDs need to survive a data-model update. Do not use
`TreeView` as a replacement for tables, tabs, or a lazy-loaded multi-surface
dashboard.

## Form Patterns

### Standard Form Field

Every interactive input SHOULD be wrapped in FormField:

```json
{"id": "name-field", "component": "FormField", "label": "Full Name", "constraintText": "Required", "showValidation": {"path": "/__showValidation"}, "checks": [{"condition": {"call": "required", "args": {"value": {"path": "/form/name"}}}, "message": "Name is required"}], "children": ["name-input"]},
{"id": "name-input", "component": "Input", "value": {"path": "/form/name"}, "placeholder": "Enter full name"}
```

### Select/Dropdown

```json
{"id": "region-field", "component": "FormField", "label": "Region", "children": ["region-select"]},
{"id": "region-select", "component": "Select", "selectedOption": {"path": "/form/region"}, "placeholder": "Select a region", "options": [{"value": "us-east-1", "label": "US East (N. Virginia)"}, {"value": "eu-west-1", "label": "EU (Ireland)"}]}
```

### Radio Group for Mutually Exclusive Choices

Use `RadioGroup` whenever mutually exclusive options need explanation, including
when the choice is the form's only field. Add concise item descriptions, bind a
sensible default, and include a `SubmitButton`:

```json
{"id": "decision-field", "component": "FormField", "label": "How should I continue?", "children": ["decision-radio"]},
{"id": "decision-radio", "component": "RadioGroup", "value": {"path": "/form/decision"}, "items": [{"value": "guided", "label": "Guided modernization", "description": "Review prioritized recommendations before deployment."}, {"value": "direct", "label": "Direct edits", "description": "Specify the infrastructure changes yourself."}]},
{"id": "submit", "component": "SubmitButton", "children": "Continue"}
```

For short actions that need no descriptions, attach native message suggestions
separately with `suggest_replies`; never put suggestion
boxes or `atx:send-message` actions in the A2UI component tree:

```json
["Approve", "Reject", "Request changes"]
```

### Checkbox / Toggle for Booleans

```json
{
  "id": "agree-check",
  "component": "Checkbox",
  "checked": { "path": "/form/agreed" },
  "children": "I agree to the terms"
}
```

### File Upload

```json
{"id": "upload-field", "component": "FormField", "label": "Documents", "children": ["upload"]},
{"id": "upload", "component": "FileUpload", "value": {"path": "/form/files"}, "allowedFileTypes": ["pdf", "csv"], "maxFiles": 5, "maxFileSizeMB": 50, "multiple": true}
```

Initialize with `"files": []` in data model.

## Display Patterns

### Key-Value Pairs Grid

```json
{
  "id": "details-kvp",
  "component": "KeyValuePairs",
  "columns": 3,
  "items": [
    { "label": "Created", "value": { "path": "/data/createdAt" } },
    { "label": "Status", "value": { "path": "/data/status" } },
    { "label": "Owner", "value": { "path": "/data/owner" } }
  ]
}
```

### Data Table

```json
{
  "id": "results-table",
  "component": "Table",
  "columnDefinitions": [
    { "id": "name", "header": "Name", "field": "name" },
    { "id": "status", "header": "Status", "field": "status" }
  ],
  "items": [
    { "id": "1", "name": "Item A", "status": "Active" },
    { "id": "2", "name": "Item B", "status": "Pending" }
  ]
}
```

Table items can be static (in updateComponents) or dynamic (in updateDataModel with path binding).

### Status Alert Banner

```json
{
  "id": "status-banner",
  "component": "Alert",
  "type": "warning",
  "header": "Action Required",
  "children": "Please review and respond within 24 hours."
}
```

Types: success, error, warning, info.

### Progress Indicator

```json
{
  "id": "progress",
  "component": "ProgressBar",
  "value": { "path": "/data/progress" },
  "label": "Migration Progress",
  "status": "in-progress"
}
```

## Anti-Patterns

### DO NOT nest component objects

Wrong:

```json
{ "id": "root", "children": [{ "id": "child", "component": "Box" }] }
```

Correct:

```json
{"id": "root", "children": ["child"]},
{"id": "child", "component": "Box", "children": "text"}
```

### DO NOT use components not in the catalog

If the catalog doesn't have a Divider component, don't use it. Use SpaceBetween or Box instead.

### DO NOT forget to initialize bound paths

If a component binds to `{"path": "/form/email"}`, the updateDataModel MUST include `"form": {"email": ""}`.

### DO NOT put version inside updateComponents

Wrong: `{"version": "v0.9", "updateComponents": {"version": "v0.9", ...}}`
Correct: `{"version": "v0.9", "updateComponents": {...}}`
