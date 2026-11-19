# A2UI Surface Generation Guide

Reference for agents generating A2UI v0.9 surfaces for the `atx-hitl/v1` catalog.

Use this guide alongside `references/catalog.json` (component/function reference).

## How to Deliver A2UI

### Inline chat surface (preferred in AWS Transform)

Embed the 3-message array directly in a fenced `atx-a2ui` block:

````
```atx-a2ui
[ ...3-message array... ]
```
````

The AWS Transform WebApp renders this with `A2UIInteractiveRenderer`. Inline
surfaces support inputs, `FormField` validation, `SubmitButton`, table
selection, side panels, and the platform actions in `references/catalog.json`. A valid
inline submission is wrapped as a chat form-submission message containing the
`/form/*` values, so the agent can parse the values and continue.

Do not describe fenced inline surfaces as read-only and do not require a
pre-wired A2A form channel. `FileUpload` can be used when the host provides an
upload context.

### A2A task artifact

When an agent explicitly returns an A2A Task, put the same 3-message array in
the task artifact metadata under the A2UI extension key:

```json
{
  "id": "task-uuid",
  "status": { "state": "input-required" },
  "artifacts": [{
    "artifactId": "a2ui-form-001",
    "parts": [
      { "kind": "text", "text": "Please provide your migration details." }
    ],
    "metadata": {
      "https://a2ui.org/a2a-extension/a2ui/v0.9": [
        { "version": "v0.9", "createSurface": { "surfaceId": "target-region-selection", "catalogId": "atx-hitl/v1" } },
        { "version": "v0.9", "updateComponents": { "surfaceId": "target-region-selection", "components": [...] } },
        { "version": "v0.9", "updateDataModel": { "surfaceId": "target-region-selection", "path": "/", "value": {...} } }
      ]
    }
  }]
}
```

**What the platform does with this:**

1. Chat Service detects the A2UI extension key in artifact metadata
2. Stores the A2UI content in S3
3. Creates a `richContent` entry on the chat message with `interactionId` and a `fragment` per artifact
4. User sees the rendered form in chat

**What you get back on submit through A2A:**

When the user submits, your agent receives the form data via A2A `message/send`:

```json
{
  "form": {
    "region": "us-west-2",
    "serverCount": "200"
  }
}
```

This is the data model at `/form/*` minus `__`-prefixed internal keys.

### Key rules

- `parts[].text` is the message text shown above the form
- The metadata key must be exactly `"https://a2ui.org/a2a-extension/a2ui/v0.9"`
- The value is the 3-message A2UI array (createSurface, updateComponents, updateDataModel)
- Set `status.state` to `"input-required"` when you need user input
- One artifact = one rendered form (fragment)
- Multiple artifacts in the same task = multiple forms shown to the user

## Flow Summary

```
Agent emits inline A2UI or returns an A2A Task with A2UI metadata
    ↓
Platform renders the interactive surface
    ↓
User sees form, fills it out, clicks Submit
    ↓
Agent receives form data through chat or A2A message/send
    ↓
Agent processes response (approve, reject, chain to next form, etc.)
```

## Message Structure

Every A2UI surface is defined by exactly 3 messages in order:

```json
[
  { "version": "v0.9", "createSurface": { ... } },
  { "version": "v0.9", "updateComponents": { ... } },
  { "version": "v0.9", "updateDataModel": { ... } }
]
```

All messages require `"version": "v0.9"`.

### 1. createSurface

```json
{
  "version": "v0.9",
  "createSurface": {
    "surfaceId": "unique-surface-id",
    "catalogId": "atx-hitl/v1"
  }
}
```

- `surfaceId`: a stable unique string identifying this surface. For an
  interactive form, use a concise customer-facing noun phrase such as
  `target-region-selection`; the WebApp displays it as
  `Form target region selection submitted`.
- `catalogId`: must be `"atx-hitl/v1"` for this catalog

### 2. updateComponents

```json
{
  "version": "v0.9",
  "updateComponents": {
    "surfaceId": "unique-surface-id",
    "components": [ ... ]
  }
}
```

The `components` array is a **flat adjacency list**. Components are NOT nested — they reference each other by string ID.

### 3. updateDataModel

```json
{
  "version": "v0.9",
  "updateDataModel": {
    "surfaceId": "unique-surface-id",
    "path": "/",
    "value": { ... }
  }
}
```

Sets the initial data model. Use `"path": "/"` to set the entire root object.

## Component Object Shape

Each component in the `components` array is a flat object:

```json
{ "id": "my-input", "component": "Input", "value": { "path": "/form/name" }, "placeholder": "Enter name" }
```

- `id` (string, required): unique identifier within the surface
- `component` (string, required): component type name from catalog
- All other props are **flat on the object** (NOT nested under a `props` key)
- One component must have `"id": "root"` — this is the tree root

### Universal `visible` Prop

Every component supports an optional `visible` prop (DynamicBoolean). When it resolves to `false`, the component renders nothing (unmounted from DOM). Omitting `visible` or setting it to `true` shows the component normally.

```json
{"id": "section-a", "component": "SpaceBetween", "children": ["..."],
 "visible": {"call": "equals", "args": {"a": {"path": "/form/tab"}, "b": "A"}}}
```

Value types:
- **Literal**: `"visible": false` / `"visible": true`
- **Path binding**: `"visible": {"path": "/form/show"}` — toggles reactively
- **Function call**: `"visible": {"call": "equals", "args": {...}}` — reactive expression (`equals`, `not_equals`, `not`, `and`, `or`)

Use cases: multi-page amendment forms, conditional sections based on radio/select choice, progressive disclosure.

**Unmount warning**: `visible: false` unmounts the React subtree — `useState` is lost. Bind state that must survive toggles to a data model path (e.g., Table filter text, MultiStepForm activeStep).

## Parent-Child Relationships

Components reference children by ID string, not by nesting:

```json
[
  { "id": "root", "component": "SpaceBetween", "children": ["header", "form"] },
  { "id": "header", "component": "Header", "children": "Page Title" },
  { "id": "form", "component": "Container", "header": "Details", "children": ["name-field"] },
  { "id": "name-field", "component": "FormField", "label": "Name", "children": ["name-input"] },
  { "id": "name-input", "component": "Input", "value": { "path": "/form/name" } }
]
```

For layout components (`SpaceBetween`, `ColumnLayout`, `Container`, `FormField`), `children` is an array of component IDs.
For display components (`Header`, `Box`), `children` is a string (the text content).
For `Alert` and `TextContent`, `children` accepts either a string or an array of component IDs (ChildList) for rich content.

For display-only text in `TextContent`, `Header`, `StatusIndicator`, `Badge`,
and `Box`, put the resolved literal string directly in `children`. Do not bind
`children` to a data-model path in the current WebApp renderer; unresolved path
objects can reach React and fail the entire surface. Continue using bindings
for actual form-control values.

A2UI display strings are literal plain text, not Markdown or HTML. Do not put
formatting syntax such as `**bold**`, Markdown headings, lists, links,
backticks, or HTML tags in component props or bound display values. Use native
catalog components for headings, emphasis, grouping, status, and layout.

## Data Binding

Props that accept `DynamicString`, `DynamicNumber`, or `DynamicBoolean` can be:

- A literal: `"placeholder": "Enter name"`
- A path binding: `"value": {"path": "/form/name"}`
- A function call: `"children": {"call": "formatCurrency", "args": {"value": {"path": "/form/amount"}, "currency": "USD"}}`

Path bindings create two-way sync for input components (`Input`, `Textarea`, `RadioGroup`, `Select`, `Checkbox`, `Toggle`, `DatePicker`, `Multiselect`, `FileUpload`, `Table`). When the user types or selects, the data model updates at that path automatically.

### Data types written by each component

| Component   | Writes to bound path                                                                                                                   | Example value                                                                      |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Input       | `string` (or `number \| undefined` when `type="number"`)                                                                               | `"Jane Doe"` or `42`                                                               |
| Textarea    | `string`                                                                                                                               | `"Long text..."`                                                                   |
| Select      | `string`                                                                                                                               | `"us-east-1"`                                                                      |
| RadioGroup  | `string`                                                                                                                               | `"option-a"`                                                                       |
| Checkbox    | `boolean`                                                                                                                              | `true`                                                                             |
| Toggle      | `boolean`                                                                                                                              | `true`                                                                             |
| DatePicker  | `string` (YYYY-MM-DD)                                                                                                                  | `"2026-05-20"`                                                                     |
| Multiselect | `Array<{value: string, label: string}>`                                                                                                | `[{"value": "opt1", "label": "Option 1"}, {"value": "opt2", "label": "Option 2"}]` |
| FileUpload  | `Array<{artifactId, name, mimeType}>`                                                                                                  | `[{"artifactId": "art-abc", "name": "report.pdf", "mimeType": "application/pdf"}]` |
| Table       | `Array<id string>` if `selectionValueField` is set, else full row objects; single-select writes a scalar (id string or one row object) | `["o1", "o2"]` (with `selectionValueField`) or `[{"id": "o1", "name": "Acme"}]`    |

Initialize each bound path in the data model with the matching empty value (`""`, `false`, `[]`). For a `Table` selection path: `[]` for multi-select, `null` for single-select.

#### How Google does it (A2UI ChoicePicker)

`Table` is a Cloudscape catalog extension — A2UI v0.9's basic catalog has no Table. Its selection write-back mirrors Google's `ChoicePicker` (the spec's multi/single selection component), which writes an **array of stable option-value strings**, never full option objects:

```json
{
  "id": "country-select",
  "component": "ChoicePicker",
  "options": [
    { "label": "USA", "value": "us" },
    { "label": "Canada", "value": "ca" }
  ],
  "selections": { "path": "/form/country" }
}
```

When the user picks "Canada", the model becomes `/form/country = ["ca"]` (the stable `value` id, in an array) — see Google's [data-binding docs](https://github.com/google/A2UI/blob/main/docs/concepts/data-binding.md) and [components reference](https://github.com/google/A2UI/blob/main/docs/reference/components.md).

> Naming note: Google's repo is internally inconsistent here — the prose reference uses the v0.8-era `selections` binding (shown above), while the normative v0.9 JSON Schema names it `value` (typed `DynamicStringList`). The write-back **shape** — an array of stable id strings — is identical either way, and that shape is what the ATX `Table` mirrors.

The ATX `Table`'s `selectionValueField` makes selection spec-aligned the same way: set it to the row's stable id column and the model stores `["o1", "o2"]` (the id strings) for multi-select; the Table reconstructs the highlighted rows on read-back by matching those ids against `items`. Single-select intentionally writes a scalar (`"o1"`) instead of ChoicePicker's 1-element array, to match Cloudscape Select ergonomics. Without `selectionValueField`, the Table writes full row objects (lossless, matches Cloudscape's `selectedItems` contract).

## Data Model Conventions

```json
{
  "form": {
    "fieldName": ""
  },
  "__showValidation": false
}
```

- `/form/*`: namespace for values the agent must receive on submit. Every path-bound input must have an initial value here (empty string `""`, `false`, or `[]`). This is the agent submission contract, not a promise that every value is passed unchanged to a downstream API. For example, `/form/configuration/kmsType` stays in `/form` so the agent receives the user's encryption choice, while the WebApplication host removes `kmsType` when it builds the `CreateConnector` API configuration because that discriminator is not an API configuration field.
- `/data/*`: namespace for host-owned UI and orchestration state. The renderer never copies values from `/data` into `/form`.
- Use canonical domain field names in `/form`, not temporary UI-state names. For example, bind a connector selector to `/form/connectorId`, never `/form/selectedConnectorId`.
- When the host creates a resource and its ID belongs in the submitted form, the host must explicitly update the canonical form path (for example `/form/connectorId`). Do not rely on the renderer to infer it from `/data`.
- `/__showValidation`: boolean, starts `false`. Controls whether FormField displays validation errors. Set to `true` on submit by the renderer.

## Validation with checks

Put `checks` on `FormField` components to define validation rules:

```json
{
  "id": "email-field",
  "component": "FormField",
  "label": "Email",
  "constraintText": "Required — valid email",
  "showValidation": { "path": "/__showValidation" },
  "checks": [
    {
      "condition": { "call": "required", "args": { "value": { "path": "/form/email" } } },
      "message": "Email is required"
    },
    {
      "condition": { "call": "email", "args": { "value": { "path": "/form/email" } } },
      "message": "Please enter a valid email"
    }
  ],
  "children": ["email-input"]
}
```

- `checks`: array of `{ condition, message }` rules
- `condition`: a `DynamicBoolean` — typically a function call returning true (valid) or false (invalid)
- `message`: error text shown when condition is false
- `showValidation`: bind to `/__showValidation` to hide errors until submit
- `constraintText`: always-visible hint about the field's requirements

Available validation functions: `required`, `regex`, `length`, `numeric`, `email`.
Compose with: `and`, `or`, `not`.
Cross-field numeric: `greater_than`, `less_than` (coerce strings to numbers).
Cross-field strict equality (no coercion): `equals`, `not_equals`.
Math: `add`, `subtract`, `multiply`, `divide`.

See `references/catalog.json` → `functions` for full signatures.

## Complete Example

A form collecting name (required) and email (required, valid format):

```json
{
  "artifacts": [{
    "artifactId": "user-account-details-001",
    "parts": [{ "kind": "text", "text": "Please create a user." }],
    "metadata": {
      "https://a2ui.org/a2a-extension/a2ui/v0.9": [
      {
        "version": "v0.9",
        "createSurface": {
          "surfaceId": "user-account-details",
          "catalogId": "atx-hitl/v1"
        }
      },
      {
        "version": "v0.9",
        "updateComponents": {
          "surfaceId": "user-account-details",
          "components": [
            {
              "id": "root",
              "component": "SpaceBetween",
              "direction": "vertical",
              "size": "l",
              "children": ["header", "form"]
            },
            { "id": "header", "component": "Header", "variant": "h2", "children": "Create User" },
            {
              "id": "form",
              "component": "SpaceBetween",
              "direction": "vertical",
              "size": "m",
              "children": ["name-field", "email-field"]
            },
            {
              "id": "name-field",
              "component": "FormField",
              "label": "Name",
              "constraintText": "Required",
              "showValidation": { "path": "/__showValidation" },
              "checks": [
                {
                  "condition": { "call": "required", "args": { "value": { "path": "/form/name" } } },
                  "message": "Name is required"
                }
              ],
              "children": ["name-input"]
            },
            { "id": "name-input", "component": "Input", "value": { "path": "/form/name" }, "placeholder": "Jane Doe" },
            {
              "id": "email-field",
              "component": "FormField",
              "label": "Email",
              "constraintText": "Required — valid email",
              "showValidation": { "path": "/__showValidation" },
              "checks": [
                {
                  "condition": { "call": "required", "args": { "value": { "path": "/form/email" } } },
                  "message": "Email is required"
                },
                {
                  "condition": { "call": "email", "args": { "value": { "path": "/form/email" } } },
                  "message": "Enter a valid email address"
                }
              ],
              "children": ["email-input"]
            },
            {
              "id": "email-input",
              "component": "Input",
              "value": { "path": "/form/email" },
              "placeholder": "jane@example.com"
            }
          ]
        }
      },
      {
        "version": "v0.9",
        "updateDataModel": {
          "surfaceId": "user-account-details",
          "path": "/",
          "value": {
            "form": { "name": "", "email": "" },
            "__showValidation": false
          }
        }
      }
      ]
    }
  }]
}
```

## Return Payload (What Your Agent Receives on Submit)

When the user submits, the platform delivers the form data to your agent via A2A `message/send`. The payload is the data model at `/form/*` minus `__`-prefixed internal keys.

Example: if your surface defines these bindings:

```json
{ "id": "amount-input", "component": "Input", "value": { "path": "/form/cashClaimAmount" } }
{ "id": "account-input", "component": "Input", "value": { "path": "/form/awsAccountId" } }
{ "id": "email-input", "component": "Input", "value": { "path": "/form/email" } }
```

On submission, the agent receives:

```json
{
  "form": {
    "cashClaimAmount": "5000.00",
    "awsAccountId": "123456789012",
    "email": "jane@partner.com"
  }
}
```

Internal keys (prefixed with `__`, e.g., `__showValidation`) are stripped before submission.

## Multi-Surface Correlation

Each A2UI surface has a unique `surfaceId`. This is your correlation key across multi-page flows.

```json
{ "createSurface": { "surfaceId": "opportunity-details", "catalogId": "atx-hitl/v1" } }
```

If you have multiple forms (e.g., `surfaceId: "opportunity-details"` followed by `surfaceId: "customer-info"`), each submission returns tagged with its surface ID. Your agent can use `surfaceId` to identify which form the user just completed and determine the next step in the workflow.

## Envelope

The 3 A2UI messages go in your A2A task artifact under the metadata extension key:

```json
{
  "artifacts": [{
    "artifactId": "your-artifact-id",
    "parts": [{ "kind": "text", "text": "Message shown above the form" }],
    "metadata": {
      "https://a2ui.org/a2a-extension/a2ui/v0.9": [ ...the 3 messages... ]
    }
  }]
}
```

The platform reads this key and handles rendering. You don't need to know how it's delivered to the client.

## Common Patterns

### Summary

```
root (SpaceBetween) → [header, alert, metrics, table]
  header (Header) → "Assessment Results"
  alert (Alert type=success) → "Completed successfully"
  metrics (ColumnLayout columns=3) → [metric-1, metric-2, metric-3]
  table (Table) with items from /data/items
```

### Selectable + Searchable + Sortable + Paginated Table

A `Table` with `selectionType`, `filtering`, sortable columns, `pagination`, and the spec-aligned `selectionValueField`. Row data lives in `/data/*`; only the selected ids go to `/form/*`.

For a display-only table, omit `selectionType`, `selectedItems`, and
`selectionValueField`. Filtering, sorting, and pagination are optional table
capabilities; use `a2ui-ux-patterns` for job-flow presentation policy.

```json
{
  "id": "opps-table",
  "component": "Table",
  "selectionType": "multi",
  "filtering": true,
  "pagination": true,
  "pageSize": 10,
  "selectionValueField": "id",
  "trackBy": "id",
  "disabledField": "alreadyImported",
  "columnDefinitions": [
    { "id": "name", "header": "Name", "field": "name", "sortable": true, "sortType": "string" },
    { "id": "arr", "header": "ARR", "field": "arr", "sortable": true, "sortType": "number" }
  ],
  "items": { "path": "/data/opps" },
  "selectedItems": { "path": "/form/selectedOpportunities" }
}
```

Initialize **both** bound paths in `updateDataModel`: `/data/opps` to the row array (otherwise the table renders empty — missing paths fail silently) and `/form/selectedOpportunities` to `[]` (multi) or `null` (single). After the user selects two rows, the model holds `/form/selectedOpportunities = ["o1", "o2"]` — the stable id strings, mirroring A2UI ChoicePicker. Omit `selectionValueField` to write full row objects instead.

**Sorting:** set `sortable: true` on each column you want sortable; use `sortType: "number"` for numeric columns so they sort numerically (not lexicographically). Set `sortingDisabled: true` on the Table to globally disable sorting. Sort state is client-side display-only and is never written to the data model.

**Pagination:** set `pagination: true` and optionally `pageSize` (defaults to 10). The current page is client-side display-only state and is never written to the data model — only the selection round-trips.

**Select-all:** when `selectionType` is `"multi"`, Cloudscape renders a header select-all checkbox automatically (no extra props). Its scope is the rows **currently visible** — the filtered set, and when pagination is on, the **current page only** (standard Cloudscape behavior). To select more, the user pages through and select-alls each page, or clears the filter. Crucially, selections **accumulate and persist** across pages and filter changes: because selection is controlled off the data model (the source of truth) and reconstructed from the full row set, select-all on page 1 then page 2 keeps both pages' rows selected, and navigating, sorting, or clearing the filter never silently drops a selected row from the Import payload.

### Interactive Form

```
root (SpaceBetween) → [header, form-fields, submit-btn]
  header (Header) → "Confirm Details"
  form-fields (SpaceBetween) → [field-1, field-2, field-3]
    field-N (FormField with checks) → [input-N]
    input-N (Input/Select/etc with path binding to /form/*)
  submit-btn (SubmitButton) → "Submit"
```

The `SubmitButton` component triggers form validation and submission to the webapp API.
It is the ONLY way to submit a form — generic `Button` actions are ignored.
For an inline surface, the WebApp sends the validated `/form/*` values back as
a chat form-submission message. For A2A `richContent`, the values arrive via
`message/send`.
After submission, the agent should send an `updateComponents` that disables the button
and fields, or replaces the surface with a confirmation view.

### Progress Display

```
root (SpaceBetween) → [progress, status]
  progress (ProgressBar value={path:/data/percent} label="Processing..." additionalInfo="Step 2 of 5")
  status (StatusIndicator) → "X of Y items processed"
```

The agent updates the fragment content on each cycle. Message polling delivers the updated content automatically.

ProgressBar also supports `variant: "key-value"` for use inside key-value pair layouts, and `resultText` for displaying outcome text when status is `"success"` or `"error"`.

### Charts

Five chart components are available, all based on Cloudscape legacy charts:

- **BarChart** — categorical bar charts, supports `stackedBars` and `horizontalBars`
- **LineChart** — line series with optional threshold lines
- **AreaChart** — stacked area series for part-to-whole over time
- **PieChart** — pie/donut with optional `innerMetricValue` + `innerMetricDescription`
- **MixedLineBarChart** — combined bar, line, and threshold series on the same axes

All cartesian charts (BarChart, LineChart, AreaChart, MixedLineBarChart) share these props:

- `series` (array, required): data series — supports path binding via `DynamicValue`
- `xTitle`, `yTitle`: axis labels
- `height` (number, default 200): chart height in pixels
- `xScaleType`: `"linear"` | `"log"` | `"categorical"` (BarChart is always `"categorical"` and does not accept this prop; MixedLineBarChart defaults to `"categorical"`; LineChart and AreaChart default to `"linear"`)
- `yScaleType`: `"linear"` | `"log"`
- `xDomain`, `yDomain`: explicit axis ranges
- `hideFilter` (default true), `hideLegend` (default false)
- `legendTitle`, `statusType`, `detailPopoverSize`
- `emphasizeBaselineAxis` (BarChart, LineChart, MixedLineBarChart only — not AreaChart)
- `ariaLabel`, `ariaDescription`

```json
{
  "id": "latency-chart",
  "component": "LineChart",
  "series": [
    {
      "title": "p50",
      "type": "line",
      "data": [
        { "x": 1, "y": 12 },
        { "x": 2, "y": 15 }
      ]
    },
    { "title": "SLA", "type": "threshold", "y": 50 }
  ],
  "xTitle": "Day",
  "yTitle": "Latency (ms)",
  "xScaleType": "linear",
  "ariaLabel": "Service latency with SLA threshold"
}
```

PieChart uses `data` (array of `{title, value, color?}`) instead of `series`. Set `variant: "donut"` with `innerMetricValue` and `innerMetricDescription` for donut charts with a center metric.

For threshold lines, use `{title, type: "threshold", y: 100}` — if `type` is omitted on a BarChart, LineChart or AreaChart series, the renderer infers `threshold` when only `y` is present (no `data`). BarChart also supports threshold series alongside bars.

AreaChart requires all area series to share the same x values in the same order — Cloudscape stacks by array index, not by x key.

Display-only — no data binding or user interaction. Safe for inline
`atx-a2ui` surfaces.

### Mermaid Diagram

Use `MermaidDiagram` to render architecture diagrams, flowcharts, sequence diagrams, ER diagrams, and other Mermaid-supported diagram types from plain text syntax. The diagram type is inferred from the content — no need to specify it separately.

```json
{
  "id": "architecture-diagram",
  "component": "MermaidDiagram",
  "content": "flowchart TD\n  A[Source DB] -->|Extract| B[AWS DMS]\n  B -->|Replicate| C[Target DB]\n  C --> D[Validation]",
  "ariaLabel": "Migration architecture showing data flow from source through DMS to target"
}
```

- `content` (DynamicString, required): the Mermaid syntax string. Supports path bindings to update the diagram from the data model.
- `maxHeight` (number, optional, default 600): max container height in pixels before scrolling.
- `ariaLabel` (string, optional): accessible label for the diagram container.
- Display-only — no data binding or user interaction. Safe for inline
  `atx-a2ui` surfaces.
- All Mermaid diagram types work: `flowchart`, `sequenceDiagram`, `erDiagram`, `classDiagram`, `stateDiagram`, `gantt`, `pie`, `gitgraph`, etc.
- Renders with `securityLevel: 'strict'` — no embedded scripts or click handlers.

### Key/value status

Set an item's optional `statusType` to render its value as a Cloudscape `StatusIndicator`. Both `value` and `statusType` keep `DynamicString` path bindings:

```json
{
  "id": "connector-details",
  "component": "KeyValuePairs",
  "items": [
    {
      "label": "Status",
      "value": { "path": "/data/connectorStatusLabel" },
      "statusType": { "path": "/data/connectorStatusType" }
    }
  ]
}
```

Allowed status values are `error`, `warning`, `success`, `info`, `stopped`, `pending`, `in-progress`, `loading`, `not-started`, and `log`. Invalid dynamic values fall back to `info`.

### Alert with Action

Use the `action` prop on `Alert` to render components (Button, Link, etc.) in the action slot:

```json
[
  {
    "id": "retry-alert",
    "component": "Alert",
    "type": "error",
    "header": "Import failed",
    "children": "3 records could not be imported.",
    "action": ["retry-btn"]
  },
  {
    "id": "retry-btn",
    "component": "Button",
    "children": "Retry",
    "action": { "event": { "name": "retry-import" } }
  }
]
```

### Button with Icon and Loading State

```json
{
  "id": "download-btn",
  "component": "Button",
  "variant": "primary",
  "iconName": "download",
  "children": "Download Report",
  "loading": { "path": "/data/downloading" },
  "loadingText": "Generating report...",
  "action": { "event": { "name": "download" } }
}
```

### Header with Counter

Use `counter` for resource counts in table/card headers:

```json
{ "id": "table-header", "component": "Header", "variant": "h2", "counter": "(24)", "children": "Servers" }
```

### Side Panel Content

Use `SidePanelContent` to keep inline chat compact while giving users a spacious side panel for large forms or content.

```
root (SpaceBetween) → [intro, panel-trigger]
  intro (TextContent) → "I've prepared a migration form for you."
  panel-trigger (SidePanelContent label="Open migration form") → [form-container]
    form-container (SpaceBetween direction=vertical size=l) → [header, region-field, notes-field, submit]
      header (Header variant=h2) → "Migration Details"
      region-field (FormField label="Region") → [region-input]
        region-input (Select selectedOption={path:/form/region} options=[...])
      notes-field (FormField label="Notes") → [notes-input]
        notes-input (Textarea value={path:/form/notes})
      submit (SubmitButton) → "Submit"
```

**Key points:**

- Children of `SidePanelContent` are NOT rendered inline — only a button is shown
- Clicking the button opens the children in the CodePreviewPanel side panel
- The panel content is fully interactive: forms, validation, submit all work
- Give a form inside the panel a `SubmitButton` with
  `action: "atx:submitAndClosePanel"` so a completed submission can close the
  panel. Plain `atx:submit` leaves the panel open.
- Use `atx:cancelAndClosePanel` for a side-panel cancel control. It skips
  validation, sends no form values, and closes the panel after the cancellation
  message is sent.
- The `SidePanelContent` trigger button is disabled when rendered inside the panel (no panel handler is propagated to child renderers) — avoid nesting `SidePanelContent` inside panel content
- The agent cannot define the click handler — the platform injects it

### Side Panel Container

Use `SidePanelContainer` as a root wrapper when you want the entire surface to be expandable into the side panel. It renders a Cloudscape Container with a header (title, description, agent-provided actions) and a built-in "expand to panel" icon button.

```
root (SidePanelContainer title="Network Configuration" description="Review your VPC topology") → [content, export-btn]
  content (SpaceBetween direction=vertical size=m) → [status, details]
    status (StatusIndicator type=success) → "4 VPCs configured"
    details (KeyValuePairs columns=2 items=[...])
  export-btn (Button variant=normal action={event:{name:"atx:expandToPanel"}}) → "Open in panel"
```

**Key points:**

- The expand-to-panel icon button is always rendered as the last action in the header — you don't declare it
- `title` (required) renders in the Container header
- `description` (optional) renders as subtext below the title
- `actions` (optional ChildList) renders additional agent-provided components (Button, Link, etc.) before the expand button
- `children` (required ChildList) renders the container body content

### Expand to Panel Action (any Button)

Any `Button` component can trigger the "expand to panel" behavior by using the `atx:expandToPanel` action name. This moves the entire surface into the side panel for a larger viewport.

```json
{
  "id": "my-expand-btn",
  "component": "Button",
  "iconName": "view-vertical",
  "variant": "icon",
  "children": "Expand",
  "action": { "event": { "name": "atx:expandToPanel" } }
}
```

**Platform-handled actions:**

| Action name         | Behavior                                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `atx:submit`        | Triggers form validation and submission (used by `SubmitButton`)                                                                                  |
| `atx:submitAndClosePanel` | Submits as `atx:submit` does, then closes a side-panel form when the agent's next update leaves it finished. Use only as the `SubmitButton.action` inside `SidePanelContent`. |
| `atx:cancelSubmit` | Cancels without validation or form data, makes the form inert, and sends a cancellation message to the agent. Use on `SubmitButton`. |
| `atx:cancelAndClosePanel` | Cancels as `atx:cancelSubmit` does, then closes the side panel after the message is sent. Use only inside `SidePanelContent`. |
| `atx:expandToPanel` | Moves the surface to the side panel                                                                                                               |
| `atx:open-panel`    | Opens the side panel with content from `context.contentId`. The renderer extracts the referenced component's subtree and renders it in the panel. |
| `atx:send-message`  | Sends `context.message` to the platform's message handler (e.g. posts to chat or triggers an agent response).                                     |
| `atx:download-artifact` | Downloads the artifact in `context.artifactId` through the WebApp. Include `context.workspaceId` whenever available. Include `context.jobId` only for a job-scoped artifact when its owning job is known. |
| `atx:download-snapshot` | Downloads a one-page PDF snapshot of the currently visible portion of the A2UI surface containing the button. Optional `context.fileName` suggests the filename. |

These actions are intercepted by the renderer and never forwarded to the agent. Use them on any `Button`, `ActionCard`, or `ButtonDropdown` component.

### Downloading an artifact

Attach `atx:download-artifact` to a `Button` and provide the artifact
identifiers in the event context. The WebApp uses the same managed-streaming
or pre-signed download path as artifact links embedded in chat messages.

```json
{
  "id": "download-report",
  "component": "Button",
  "children": "Download report",
  "iconName": "download",
  "action": {
    "event": {
      "name": "atx:download-artifact",
      "context": {
        "workspaceId": "workspace-123",
        "jobId": "job-456",
        "artifactId": "artifact-789"
      }
    }
  }
}
```

`artifactId` is required. Include `workspaceId` whenever it is available.
Include `jobId` only when the artifact is job-scoped and its owning job is
known. Omit `jobId` for workspace-scoped artifacts even when the current chat
is inside a job. Preserve explicit source scope for artifacts from another job
or workspace. The action is safe in inline `atx-a2ui` surfaces because the
platform handles it locally without submitting form data.

### Downloading the visible surface

Attach `atx:download-snapshot` to a `Button` to save the currently visible
inline or side-panel A2UI view as a PDF:

```json
{
  "id": "download-snapshot",
  "component": "Button",
  "children": "Download snapshot",
  "iconName": "download",
  "action": {
    "event": {
      "name": "atx:download-snapshot",
      "context": { "fileName": "migration-plan-snapshot.pdf" }
    }
  }
}
```

The result is a visual snapshot, not a complete data export. It excludes
offscreen, hidden, virtualized, and other paginated content. Never provide a
DOM selector or another surface identifier.

### ActionCard

A clickable card where the entire surface is interactive. Use for navigation choices, feature entry points, or panel triggers.

```json
{
  "id": "migration-card",
  "component": "ActionCard",
  "header": "Configure Migration",
  "description": "Set up source and target parameters",
  "action": { "event": { "name": "atx:open-panel", "context": { "contentId": "migration-form" } } }
}
```

### Opening a Side Panel with atx:open-panel

Any component with an `action` prop can open the side panel by dispatching `atx:open-panel` with a `context.contentId`. The content referenced by that ID doesn't need to be in the root render tree — orphaned components (not reachable from root via children arrays) remain hidden until the panel opens.

```json
[
  { "id": "root", "component": "SpaceBetween", "direction": "vertical", "children": ["trigger"] },
  {
    "id": "trigger",
    "component": "ActionCard",
    "header": "View Details",
    "description": "Open the migration form in the side panel",
    "action": { "event": { "name": "atx:open-panel", "context": { "contentId": "panel-form" } } }
  },
  {
    "id": "panel-form",
    "component": "SpaceBetween",
    "direction": "vertical",
    "size": "l",
    "children": ["panel-header", "name-field", "submit"]
  },
  { "id": "panel-header", "component": "Header", "variant": "h2", "children": "Migration Details" },
  { "id": "name-field", "component": "FormField", "label": "Name", "children": ["name-input"] },
  { "id": "name-input", "component": "Input", "value": { "path": "/form/name" } },
  { "id": "submit", "component": "SubmitButton", "children": "Submit" }
]
```

**Key points:**

- `panel-form` and its children are NOT in `root`'s tree — they're orphaned and invisible until the panel opens
- A `Button` works the same way: `{ "component": "Button", "children": "Open", "action": { "event": { "name": "atx:open-panel", "context": { "contentId": "panel-form" } } } }`
- `SidePanelContent` still works for backward compatibility — it's a self-contained trigger + content in one component
- The panel content is fully interactive (forms, validation, submit all work)

## Do's and Don'ts

**DO:**

- Use `catalogId: "atx-hitl/v1"` always
- Initialize every bound path in `updateDataModel`
- Use kebab-case for all IDs and surfaceId
- Keep surfaces focused — one concern per surface
- Use `StatusIndicator` for status, `Alert` for messages, `ProgressBar` for progress
- Use `KeyValuePairs` for labeled data, `Table` for lists

**DON'T:**

- Don't nest components — use flat array with ID references
- Don't use component names not in the catalog
- Don't reference paths that aren't initialized in the data model
- Don't use action names absent from the catalog. Platform actions such as
  `atx:download-artifact`, `atx:open-panel`, and `atx:submit` work in inline
  `atx-a2ui` surfaces.
- Don't generate partial arrays — always produce all 3 messages
- Don't claim inline `atx-a2ui` forms are read-only or require customers to
  retype submitted values
- Don't use generic `Button` for form submission — use `SubmitButton` instead
- Don't place form values in `atx:cancelSubmit` or
  `atx:cancelAndClosePanel` action context
- Don't define an action or click handler on `SidePanelContent` — the platform injects it automatically

## Generation Rules & Self-Validation Checklist

Before outputting JSON, verify:

1. Exactly one component has `"id": "root"`
2. Every component ID is unique within the surface
3. Every ID referenced in a `children` array exists as a component in the same `components` array
4. Props are FLAT on the component object — do NOT nest under a `props` key
5. Every `{"path": "/form/fieldName"}` binding has a corresponding initial value in `updateDataModel`
6. `__showValidation` is initialized to `false` if any FormField uses `checks`
7. FormField `children` contains exactly one input component ID
8. `checks` conditions use function names from the catalog's `functions` section — unknown names throw at runtime
9. Return ONLY valid JSON — no markdown fences, no explanation text, no trailing commas
10. Component type names are case-sensitive and must match the catalog exactly (e.g., `"FormField"` not `"formField"`)
11. `surfaceId` is consistent across all 3 messages
12. `"version": "v0.9"` on all messages
13. `"catalogId": "atx-hitl/v1"` in createSurface
14. Every `atx:`-prefixed `action.event.name` is listed in the catalog's
    `platformActions` section. Other action names are custom actions forwarded
    to the agent.
15. All required form fields have validation and `/__showValidation` is initialized as `false`
16. A `FileUpload` is used only when the host provides an upload context

## Reference

- **Catalog (source of truth)**: See [catalog.json](./catalog.json) for the complete component and function definitions with all default values
- Composition patterns: [composition-patterns.md](./composition-patterns.md)
- Validation patterns: [validation-patterns.md](./validation-patterns.md)
- Data binding: [data-binding-advanced.md](./data-binding-advanced.md)
