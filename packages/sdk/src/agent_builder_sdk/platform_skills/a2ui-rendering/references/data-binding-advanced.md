# Data Binding — Advanced Patterns

## JSON Pointer Basics (RFC 6901)

All paths in A2UI are JSON Pointers:

- `/` = root of data model
- `/form/name` = `dataModel.form.name`
- `/items/0/title` = first element's title in items array
- Keys with `/` or `~` must be escaped: `~0` for `~`, `~1` for `/`

## Two-Way Binding

Interactive components (Input, Textarea, Select, RadioGroup, Checkbox, Toggle, DatePicker, Multiselect, FileUpload, Table) establish two-way binding:

1. Component reads current value from the path
2. User changes the value → component writes to the path
3. Any other component bound to the same path updates reactively

The server is NOT notified of changes until an explicit action fires.

## Path Conventions

| Pattern           | Purpose                      | Example               |
| ----------------- | ---------------------------- | --------------------- |
| `/form/<field>`   | User-editable form inputs    | `/form/email`         |
| `/data/<section>` | Read-only display data       | `/data/metrics/total` |
| `/__<internal>`   | Renderer internal state      | `/__showValidation`   |
| `/errors/<field>` | Legacy manual error messages | `/errors/name`        |

## Initializing the Data Model

Every path that a component binds to MUST exist in the initial updateDataModel. Missing paths cause silent binding failures.

### Type-appropriate defaults

| Component type                    | Initialize as       |
| --------------------------------- | ------------------- |
| Input (type="text"), Textarea, DatePicker | `""` (empty string) |
| Input (type="number")             | `0` or `null`       |
| Select, RadioGroup                | `""` (empty string) |
| Checkbox, Toggle                  | `false`             |
| Multiselect                       | `[]` (empty array)  |
| FileUpload                        | `[]` (empty array)  |
| Table (selectedItems, multi)      | `[]` (empty array)  |
| Table (selectedItems, single)     | `null`              |
| Numeric (ProgressBar value, etc.) | `0`                 |

> **Table selection shape.** With `selectionValueField` set, the `selectedItems` path stores **stable id strings** — `["o1", "o2"]` for multi, a scalar `"o1"` for single — mirroring A2UI's `ChoicePicker`, which writes an array of option-value ids (`/form/country = ["ca"]`; see Google's [data-binding docs](https://github.com/google/A2UI/blob/main/docs/concepts/data-binding.md)). The Table reconstructs the highlighted rows on read-back by matching those ids against `items` (via `trackBy`/`selectionValueField`). Without `selectionValueField`, it stores full row objects instead. Single-select writes a scalar (not a 1-element array) — an intentional divergence from ChoicePicker to match Cloudscape Select ergonomics.

> **Table display-only state (filter, sort, pagination).** A Table's filter text, sort column/direction, and current page are **client-side display-only state** — they are NOT written to the data model. Only `selectedItems` round-trips. Set `pagination: true` (with optional `pageSize`, default 10) and `sortable: true` (plus `sortType: "number"` for numeric columns) per the catalog. **Select-all scope:** the header select-all covers the rows _currently visible_ — the filtered set, or the _current page_ when pagination is on (standard Cloudscape behavior; one click does not select hidden pages). Selections nonetheless **accumulate and persist** across pages and filter changes because the model is the source of truth and selection is reconstructed from the full row set — so select-all on each page adds up, and navigating, sorting, or clearing the filter never silently drops a selected row.

### Example

```json
{
  "version": "v0.9",
  "updateDataModel": {
    "surfaceId": "migration-request-details",
    "path": "/",
    "value": {
      "form": {
        "name": "",
        "email": "",
        "region": "",
        "priority": "",
        "agreed": false,
        "tags": [],
        "attachments": []
      },
      "data": {
        "title": "Request Form",
        "deadline": "2026-07-01"
      },
      "__showValidation": false
    }
  }
}
```

## Dynamic Templates (List Rendering)

For rendering a list of items from data, use ChildList with template syntax:

```json
{ "id": "item-list", "component": "SpaceBetween", "children": { "componentId": "item-template", "path": "/items" } }
```

This renders one instance of `item-template` for each element in the `/items` array.

### Scoped Paths in Templates

Inside a template, paths WITHOUT a leading `/` are relative to the current array item:

```json
{"id": "item-template", "component": "Container", "children": ["item-name", "item-status"]},
{"id": "item-name", "component": "Box", "variant": "strong", "children": {"path": "name"}},
{"id": "item-status", "component": "StatusIndicator", "type": "info", "children": {"path": "status"}}
```

With data `"/items": [{"name": "Task A", "status": "Active"}, {"name": "Task B", "status": "Done"}]`:

- First instance: `name` resolves to `/items/0/name` → "Task A"
- Second instance: `name` resolves to `/items/1/name` → "Task B"

Absolute paths (with leading `/`) still resolve from root, even inside templates:

```json
{ "id": "item-header", "component": "Box", "children": { "path": "/globalTitle" } }
```

## Function Calls for Computed Values

When you need formatted or computed display values:

### formatString (string interpolation)

```json
{
  "id": "greeting",
  "component": "TextContent",
  "children": { "call": "formatString", "args": { "value": "Hello, ${/user/firstName} ${/user/lastName}!" } }
}
```

The `${/path}` syntax interpolates data model values into the string.

### formatDate

```json
{
  "id": "date-display",
  "component": "Box",
  "children": { "call": "formatDate", "args": { "value": { "path": "/data/createdAt" }, "format": "MMM d, yyyy" } }
}
```

### formatCurrency

```json
{
  "id": "total",
  "component": "Box",
  "variant": "awsui-value-large",
  "children": { "call": "formatCurrency", "args": { "value": { "path": "/data/amount" }, "currency": "USD" } }
}
```

### formatNumber

```json
{
  "id": "count",
  "component": "Box",
  "children": { "call": "formatNumber", "args": { "value": { "path": "/data/count" }, "grouping": true } }
}
```

### pluralize

```json
{
  "id": "item-count",
  "component": "Box",
  "children": {
    "call": "pluralize",
    "args": { "value": { "path": "/data/count" }, "zero": "No items", "one": "1 item", "other": "${/data/count} items" }
  }
}
```

## Action Context Resolution

When a Button dispatches an action, context values are resolved at dispatch time:

```json
{
  "id": "submit-btn",
  "component": "Button",
  "children": "Submit",
  "action": {
    "event": {
      "name": "form_submit",
      "context": {
        "formData": { "path": "/form" },
        "timestamp": { "call": "formatDate", "args": { "value": "now", "format": "yyyy-MM-dd'T'HH:mm:ss" } }
      }
    }
  }
}
```

The host application receives the resolved values (actual data, not path references).

## Incremental Data Updates

After the initial updateDataModel, the server can send targeted updates:

```json
{ "version": "v0.9", "updateDataModel": { "surfaceId": "my-surface", "path": "/data/status", "value": "completed" } }
```

This updates ONLY `/data/status` without touching other data. Useful for streaming partial results.

To delete a path, omit the `value` field:

```json
{ "version": "v0.9", "updateDataModel": { "surfaceId": "my-surface", "path": "/data/tempField" } }
```

## Multiple Surfaces

A single message stream can manage multiple surfaces:

```json
[
  {"version": "v0.9", "createSurface": {"surfaceId": "sidebar", "catalogId": "..."}},
  {"version": "v0.9", "createSurface": {"surfaceId": "main-content", "catalogId": "..."}},
  {"version": "v0.9", "updateComponents": {"surfaceId": "sidebar", "components": [...]}},
  {"version": "v0.9", "updateComponents": {"surfaceId": "main-content", "components": [...]}}
]
```

Each surface has its own independent data model. Cross-surface data sharing is NOT supported at the protocol level.
