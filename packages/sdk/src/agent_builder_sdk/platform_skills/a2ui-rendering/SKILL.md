---
name: a2ui-rendering
description: Render structured information and collect user input using A2UI surfaces instead of plain text. Activates when presenting tables, lists, comparisons, step summaries, forms, or any data that benefits from UI components, and when collecting multiple inputs from the user (forms, configuration wizards, approvals with details).
---

# A2UI Dynamic Rendering

You can render rich UI surfaces in AWS Transform chat using the A2UI v0.9 protocol and the
`atx-hitl/v1` component catalog. Use this whenever you present structured information or
collect user input.

## WebApp-Only Eligibility Gate

Use A2UI only in an AWS Transform WebApp job where the `render_a2ui_surface` tool is
available. The WebApp owns the renderer and the interactive platform actions.

Never emit `atx-a2ui` through an MCP client, a CLI, or any other non-WebApp transport. Those
paths do not render the protocol; use concise plain text or Markdown there.

## UX Policy

Load `a2ui-ux-patterns` to decide when A2UI is appropriate and which presentation or
interaction pattern to use. That skill owns the UX policy for tables, summaries, forms,
suggestions, uploads, downloads, side panels, alerts, charts, and next actions. This skill
owns only the component catalog, protocol, bindings, validation, and delivery contract.

## How to Render

### Inline chat surface (preferred)

1. Call `render_a2ui_surface` with a `surface_id`, one nested `component_tree`, and a
   `data_model`. It returns a fenced `atx-a2ui` block.
2. Finish all other tool calls of the turn before you write the reply; that includes
   `suggest_replies` when you use it. Text in a message that also calls a tool is not part of
   the reply.
3. Write the reply last, in a message with no tool call, with the block in it **unchanged**.
   The WebApp renders it in place.
4. If the tool returns `Error:`, it lists every problem it found. Fix all of them in one pass
   and call it once more. If that is rejected too, stop using A2UI for this turn and reply in
   concise plain text. A surface that rendered without an error earlier in the turn stays in
   the reply; do not repeat its content in the text.

Do not hand-author an `atx-a2ui` block; the tool validates it against the catalog.

Describe one nested root component. When `children`, `footer`, `actions` or a `Header` `description`
holds child components, nest those component objects directly. Keep text-valued `children`
as text. Put the catalog's platform action value or event object directly in `action`; do not
wrap an action event as a component. For `Tabs` and `MultiStepForm`, put a nested component
in each tab or step's `content`. Omit component IDs unless a stable ID is genuinely needed
(for example, the target of `atx:open-panel`); the tool assigns IDs, gives the root the ID
`root`, and flattens the tree into the A2UI wire format.

Keep display and form values in `data_model` and bind components to those paths instead of
repeating the same data in component definitions. Every bound path needs an initial value.

The renderer supports inputs, validation, `SubmitButton`, side panels, and platform actions
inline. A valid `SubmitButton` submission comes back through chat with the `/form/*` values.
Do not claim an inline surface is read-only or ask the customer to retype form values.

### A2A task artifact

An agent that explicitly returns an A2A Task can carry the same surface in a task artifact:
put `agent_builder_sdk.ui_chat.a2ui.build_a2ui_messages(...)` in the artifact metadata under
`A2UI_EXTENSION_KEY` (`https://a2ui.org/a2a-extension/a2ui/v0.9`). See
`references/a2ui-surface-guide.md` for the envelope.

The wire format always contains three messages:
1. `createSurface`: declares the surface ID and catalog
2. `updateComponents`: the flat component list (your UI)
3. `updateDataModel`: initial data bindings (`{}` if none)

## References

Read these with `read_platform_skill_file(skill_name="a2ui-rendering", path=...)`:

- `references/a2ui-surface-guide.md`: full protocol, component shapes, data binding,
  validation, side panels, and examples (the examples use the flat wire format).
- `references/composition-patterns.md`: layout patterns that combine components.
- `references/data-binding-advanced.md`: templates, functions, and computed values.
- `references/validation-patterns.md`: form validation rules and per-component notes.
- `references/catalog.json`: every component, its props, platform actions, and functions.

## Available Components

| Use Case | Component |
|----------|-----------|
| Tables | `Table` with columns and rows |
| Key-value pairs | `KeyValuePairs` (supports `statusType` on items) |
| Cards/tiles | `Container` + `SpaceBetween`, `Cards`, `ActionCard` |
| Forms | `FormField` + input components + `SubmitButton` |
| Multi-step forms | `MultiStepForm` |
| Expandable details | `ExpandableSection` |
| Tabs | `Tabs` |
| Hierarchies | `TreeView` |
| Step progress | `ProgressBar` |
| Choices | `RadioGroup`, `Select`, `Tiles`, `SegmentedControl` |
| Text input | `Input`, `Textarea`, `Autosuggest` |
| Multi-select | `Multiselect`, `TokenGroup` |
| File upload | `FileUpload` |
| Alerts/status | `Alert`, `StatusIndicator` |
| Charts | `BarChart`, `LineChart`, `AreaChart`, `PieChart`, `MixedLineBarChart` |
| Diagrams | `MermaidDiagram` |
| Layout | `ColumnLayout`, `Grid`, `SpaceBetween` |
| Side panel | `SidePanelContent`, `SidePanelContainer` |
| Actions | `Button`, `ButtonDropdown`, `CopyToClipboard` |
| Continue chat | Reply suggestions attached with `suggest_replies` |
| Artifact download | `Button` with `atx:download-artifact` |
| View snapshot | `Button` with `atx:download-snapshot` |

### Mermaid Diagrams

Use `MermaidDiagram` with the required `content` prop. Never use `diagram`; that prop does not
exist in the catalog.

```json
{
  "component": "MermaidDiagram",
  "content": "flowchart TD\n  A[Source] --> B[Target]",
  "ariaLabel": "Architecture flow from source to target"
}
```

Use ordinary ASCII spaces for Mermaid indentation, never non-breaking spaces (`U+00A0`).

## Data Collection Pattern

When you need user input, pass a nested form tree with `FormField` wrappers and a
`SubmitButton` to `render_a2ui_surface`:

```json
{
  "surface_id": "customer-name",
  "component_tree": {
    "component": "SpaceBetween",
    "direction": "vertical",
    "size": "m",
    "children": [
      {
        "component": "FormField",
        "label": "Name",
        "children": [{ "component": "Input", "value": { "path": "/form/name" } }]
      },
      { "component": "SubmitButton", "children": "Submit" }
    ]
  },
  "data_model": { "form": { "name": "" } }
}
```

The user fills in the form and clicks Submit. The `SubmitButton` dispatches `atx:submit`,
validates all `checks`, and delivers the `/form/*` data as a chat form-submission message (or
A2A `message/send` for a task artifact). Parse those values and continue the workflow; do not
ask the user to repeat them.

Use reply suggestions (`suggest_replies`) instead when no validated form payload is needed and
a click should simply continue the conversation as the customer.

For a form inside `SidePanelContent`, set the `SubmitButton` `action` prop to
`"atx:submitAndClosePanel"` so a completed form can close the panel.

Use a `SubmitButton` with `action: "atx:cancelSubmit"` when the customer must be able to
abandon an inline form. Cancellation skips validation, sends no form values, makes the form
terminal, and tells you the customer chose not to submit. Inside `SidePanelContent`, use
`action: "atx:cancelAndClosePanel"`.

```json
{ "component": "SubmitButton", "children": "Cancel", "variant": "normal", "action": "atx:cancelSubmit" }
```

Do not put abandoned form values in a cancellation action context and do not try to infer or
recover them after cancellation.

### TreeView

Use `TreeView` for expandable hierarchical data. Every item needs a stable, globally unique
`id` and string `content`; nested items go in `children`. Always provide `ariaLabel`.

```json
{
  "component": "TreeView",
  "ariaLabel": "Migration resource hierarchy",
  "connectorLines": "vertical",
  "expandedItems": { "path": "/form/expandedItems" },
  "items": [
    {
      "id": "applications",
      "content": "Applications",
      "secondaryContent": "2 applications",
      "children": [
        { "id": "storefront", "content": "Storefront" },
        { "id": "fulfillment", "content": "Fulfillment" }
      ]
    }
  ]
}
```

Bind `expandedItems` only when expansion state needs to survive data-model updates. Split very
large hierarchies across smaller surfaces instead of one unbounded tree.

## Renderer Failure Feedback

The WebApp can send a hidden `[[atx-a2ui-render-issue:v1 ...]]` envelope when the customer
selects **Debug render issue** on a failed surface. It correlates the original message and
`surface-id`, names the render phase, and may include an error name, message, and component
stack.

Treat it as machine-readable repair feedback: correct the catalog or protocol violation and
render the complete surface again with the same intended content. Do not echo the envelope or
raw diagnostics to the customer.

## Artifact Download Pattern

Use a `Button` with the platform-handled `atx:download-artifact` action when the customer
should be able to download an existing artifact:

```json
{
  "component": "Button",
  "children": "Download report",
  "iconName": "download",
  "action": {
    "event": {
      "name": "atx:download-artifact",
      "context": { "workspaceId": "workspace-123", "jobId": "job-456", "artifactId": "artifact-789" }
    }
  }
}
```

`artifactId` is required: use the exact ID you got when you uploaded the artifact. Include
`workspaceId` whenever it is available. Include `jobId` only when the artifact is job-scoped and
its owning job is known; omit it for workspace-scoped artifacts. The host performs the download
locally; do not substitute a URL or expect the action to come back to you.

## Visible Surface Snapshot Pattern

Use a `Button` with `atx:download-snapshot` when the customer should save a PDF snapshot of the
A2UI content currently in view:

```json
{
  "component": "Button",
  "children": "Download snapshot",
  "iconName": "download",
  "action": { "event": { "name": "atx:download-snapshot", "context": { "fileName": "migration-plan-snapshot.pdf" } } }
}
```

This is a visual snapshot of the visible portion of the surface, not an export. Do not provide
a selector, target surface, artifact ID, or hidden data.

## Conditional Visibility

Every component supports a universal `visible` prop (DynamicBoolean, optional). When it
resolves to `false`, the component renders nothing.

- **Literal**: `"visible": false`
- **Path binding**: `"visible": {"path": "/form/showSection"}` (toggles when the value changes)
- **Function call**: `"visible": {"call": "equals", "args": {"a": {"path": "/form/x"}, "b": "Y"}}`
  using `equals`, `not_equals`, `not`, `and`, `or`

`visible: false` unmounts the component, so local state is lost. Bind toggle-sensitive state
(filters, pagination, active step) to a data-model path so it survives visibility changes.

## Self-Validation

`render_a2ui_surface` checks component names, props, required props, value forms (text,
component list, array, boolean, number), enum values, item keys, the row field names of `Table`
and `Cards`, function names, IDs, child references, non-breaking spaces, and that every bound
path has an initial value. You still own:

1. The content of a plain `string` prop (for example, `Link` `href`): the tool checks that the
   value is text, not what the text says.
2. Every string inside the surface is literal plain text. No HTML or Markdown in component
   props or bound display values; use catalog components for headings, emphasis, and layout.
3. Use `SpaceBetween` for vertical layouts and `ColumnLayout` (inside a `Container`) for grids.

## Surface ID Convention

- `{workflow}-{purpose}`, for example `migration-server-inventory` or `planning-wave-review`.
- For interactive forms, a concise customer-facing kebab-case noun phrase that reads naturally
  in the WebApp confirmation `Form <surface name> submitted`, such as `migration-preferences`.
  Do not use action phrases, append `-form`, or include `surface`, `submitted`, UUIDs, or
  version numbers. See `a2ui-ux-patterns`.
- For ephemeral displays: `display-{uuid}`.
- To change a surface in the same turn, render it again with the same ID.

## Example: Rendering a Server Table

Use this interactive configuration as the default for inventories and other multi-row data. Do
not simplify it to a plain Markdown table.

```json
{
  "surface_id": "display-servers",
  "component_tree": {
    "component": "Table",
    "columnDefinitions": [
      { "id": "name", "header": "Server", "field": "name", "sortable": true, "sortType": "string" },
      { "id": "os", "header": "OS", "field": "os", "sortable": true, "sortType": "string" },
      { "id": "cpu", "header": "CPU", "field": "cpu", "sortable": true, "sortType": "number" },
      { "id": "memory", "header": "Memory", "field": "memory", "sortable": true, "sortType": "number" }
    ],
    "items": { "path": "/data/servers" }
  },
  "data_model": {
    "data": {
      "servers": [
        { "name": "web-01", "os": "Linux", "cpu": "4 vCPU", "memory": "16 GB" },
        { "name": "db-01", "os": "Windows", "cpu": "8 vCPU", "memory": "32 GB" }
      ]
    }
  }
}
```
