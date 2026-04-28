# HITL Render Engine — Limitations and Supported Capabilities

## Input Capture Support

### SUPPORTED — input IS captured on form submission

| Component | What It Captures | Notes |
|-----------|-----------------|-------|
| Input | String value | Single-line text. fieldId strongly recommended (auto-generated ID like `:r1:` used if omitted -- unusable by agent). Wrapped in extra SpaceBetween. |
| Textarea | String value | Multi-line text. fieldId strongly recommended. |
| RadioGroup | Selected item's value string | Single selection. Auto-selects first item visually if no default, BUT value is NOT reported to context unless user interacts. Uses `readOnly` (not `disabled`) when task is completed. fieldId strongly recommended. |
| FileUpload | Array of {name, content (base64), isZip} | Files base64 encoded in browser memory. No file size limit enforced. Does not pass `disabled` to Cloudscape -- silently ignores changes when task completed. fieldId strongly recommended. |

These four components have custom wrappers that call `useFieldInput(fieldId)` to report values to the HITL context. On submission, all values are sent as `{fieldId1: value1, fieldId2: value2, ...}`.

**Important:** If the user never interacts with a RadioGroup, the agent receives NO value for that fieldId -- the auto-selected first item is visual only. To guarantee a value, set the `value` prop explicitly and note that the agent should treat absence of the key as "user accepted default."

### Response shapes by component

When the agent downloads the human artifact after submission, each fieldId maps to a value with a specific shape:

**Input** — plain string:
```json
{"userName": "Jane Doe"}
```

**Textarea** — plain string:
```json
{"feedbackComments": "The migration plan looks good. Proceed with phase 1."}
```

**RadioGroup** — the `value` string of the selected item (not the label):
```json
{"connectorType": "existing"}
```
Note: RadioGroup auto-selects the first item visually, but the value is NOT reported to context unless the user interacts. The agent should treat absence of the key as "user accepted default."

**FileUpload** — object with `uploadedFiles` array, each file base64-encoded:
```json
{
  "awsAccountsFile": {
    "uploadedFiles": [
      {
        "name": "accounts.csv",
        "content": "YWNjb3VudF9pZCxuYW1lCjEyMzQ1Njc4OTAxMixQcm9k...",
        "isZip": false
      }
    ]
  }
}
```
The `content` field is base64-encoded. The agent must decode it:
```python
import base64
file_data = data["awsAccountsFile"]["uploadedFiles"][0]
raw_content = base64.b64decode(file_data["content"]).decode("utf-8")
```
For `multiple: true`, the `uploadedFiles` array contains multiple entries.

### NOT SUPPORTED — renders visually but input is silently lost

| Component | Why It Fails |
|-----------|-------------|
| Select | No custom wrapper. Raw Cloudscape Select has no fieldId integration. User picks an option, submits, agent receives nothing. |
| Multiselect | Same. No wrapper. Selections lost. |
| Checkbox | Same. No wrapper. Checked state lost. |
| Toggle | Same. No wrapper. Toggle state lost. |
| DatePicker | Same. No wrapper. Selected date lost. |
| TimeInput | Same. No wrapper. Entered time lost. |
| DateInput | Same. No wrapper. Entered date lost. |
| DateRangePicker | Same. No wrapper. Selected range lost. |
| Autosuggest | Same. No wrapper. Selected suggestion lost. |

### Workarounds

| Need | Use Instead |
|------|------------|
| Dropdown single selection | RadioGroup with the same options |
| Boolean yes/no | RadioGroup with items: [{value: "yes", label: "Yes"}, {value: "no", label: "No"}] |
| Date input | Input with placeholder "YYYY-MM-DD" |
| Time input | Input with placeholder "HH:MM" |
| Multiple selection | Multiple RadioGroups, or Textarea asking user to list selections |

## What the Engine Cannot Do

### No function callbacks
The JSON is purely declarative. Any prop that accepts a function is ignored:
- No onChange, onDismiss, onFollow, onSelect, onClick handlers
- Dismissible alerts render the X button but clicking it does nothing
- Links navigate via href only, no programmatic navigation
- Buttons render but cannot trigger custom actions

### No conditional rendering
The JSON is static. No mechanism to:
- Show/hide components based on user input
- Enable/disable fields based on other field values
- Create dependent dropdowns (select country then filter cities)
- Progressive disclosure (reveal fields as user fills earlier ones)

Every field is always visible. Complex conditional forms require a custom registered component.

### Recommended workaround: break into multiple HITL tasks
If a workflow requires interactive components that depend on each other (e.g., select a database type, then configure type-specific settings), break it into sequential HITL tasks instead of one complex form:

1. First HITL task: collect the initial selection (e.g., RadioGroup for database type)
2. Agent processes the response and builds the next UI based on the selection
3. Second HITL task: show only the fields relevant to that selection

This keeps each task simple, avoids the need for conditional rendering, and lets the agent make decisions between steps. Use `CLOSED_PENDING_NEXT_TASK` closure type to chain tasks together.

### No client-side validation
FormField supports errorText and warningText props but they are static — set once in the JSON. No way to:
- Show "required" after user leaves a field blank
- Validate format as user types
- Prevent submission until fields are filled
- Show/hide error messages dynamically

All validation happens after submission, on the agent side.

### No streaming or progressive rendering
The full JSON must be generated, saved as an artifact, and loaded before anything renders. No incremental rendering. Users see a loading state until the entire JSON is ready.

### No state persistence across refreshes
When the agent sends a refresh (new artifact via QT_REFRESH), the entire component tree re-renders from scratch. All user input in progress is lost. useState hooks in wrapped components reset to initial values.

### No error boundary
If the JSON contains a component that causes a render error, the entire HITL UI crashes to a white screen. No fallback UI. The fallbackComponentID concept from the design doc is not implemented.

### No depth or size limits
The recursive renderNode function has no depth guard. Deeply nested or extremely large JSON (thousands of nodes) could cause stack overflow or browser tab crash.

### No file size limits on FileUpload
Files are base64 encoded into memory via FileReader.readAsDataURL. A 200MB file becomes approximately 267MB base64 in memory. No maxSize enforcement. Browser tab will freeze or crash on large files.

### Disabled state varies per component
When a task is completed/submitted or the job is terminal, inputs are disabled -- but the mechanism differs:
- **Input, Textarea**: `disabled` prop passed to Cloudscape component (grayed out)
- **RadioGroup**: `readOnly` prop (normal styling, but not interactive)
- **FileUpload**: silently ignores change events (no visual indicator)

### No i18n for generated content
Wrapped components have hardcoded English strings: "No resources", "No matched resources", "Loading resources", "Choose file", "Drop file to upload". No mechanism for locale or translated strings in the JSON.

### No fieldId collision detection
If two inputs share the same fieldId, the second value silently overwrites the first. No duplicate warning.

### No multi-step wizard support
Wizard component renders visually but step transitions do not work. No state management for step navigation, per-step validation, or progress tracking.

### No undo/redo for user input
Context state is append-only. User accidentally clears a textarea — the previous value is gone. No history.

### Submit button disabled on display-only tasks
The submit button is disabled until at least one input component reports a value. For display-only HITL tasks (dashboards, status views) with no Input, Textarea, RadioGroup, or FileUpload, the submit button stays disabled and the user cannot proceed. Include at least one input component if the user needs to acknowledge or take action.

## Component-Specific Limitations

### PieChart
Only accepts the `data` prop: `[{title, value, color?}]`. All other PieChart props are ignored by the wrapper. Cannot customize: size, variant (no donut), legend title, inner metric value, inner metric description, loading state, error state.

### Table
The wrapper automatically adds pagination (20/page), text filter, column preferences, sorting, and expandable rows. These cannot be disabled or configured via JSON. The wrapper defaults to `variant="container"` if not specified -- override with `variant: "borderless"` or `variant: "full-page"`. stickyHeader is hardcoded true.

Table cell values that are valid JSON strings are automatically parsed and rendered as components. This is implicit -- there is no opt-in flag. A cell value that happens to be valid JSON but is meant as plain text will be rendered as a component.

### ContentLoader
Fixed hardcoded skeleton pattern. Cannot customize shape, size, or number of skeleton lines. Every loading state looks identical.

### Markdown
Supports GFM (tables, strikethrough), syntax highlighting, deeplinks, and raw HTML (`rehypeRaw`). Single newlines render as `<br>` (`remarkBreaks` enabled). All links open in a new tab with Cloudscape Link external icon. Deeplinks matching `/workspaces/{id}/jobs/{id}/artifacts/{id}` trigger artifact downloads via the HITL context. Does not support embedded components -- it is pure markdown text rendering only.

## Platform Rules (ESLint enforced)

| Rule | What It Means for JSON |
|------|----------------------|
| Container is banned | Do not use Container in HITL JSON. Use SpaceBetween + Header instead. |
| Table variant must be "borderless" or "full-page" | Always set variant: "borderless" on Table. Default "container" is rejected. |
| Box variant h1/h2/h3 is banned | Use Header for h1-h3 headings, not Box. Box variant h4/h5 is OK. |
| Raw HTML headings (h1-h6) banned | Do not use `{"type": "h1"}` etc. Use Header component instead. Unknown types fall back to raw HTML elements. |
| ExpandableSection variant "container" is banned | Omit variant or use "default". |
| stickyHeader required on Table and Cards | Table wrapper hardcodes this. Cards needs it explicitly. |

## Rendering Engine Behavior

### Top-level wrapping
The engine wraps all rendered JSON in `<SpaceBetween size="m">` and adds a `TitleBadgeDescription` header from task metadata. Your root component is a child of this outer SpaceBetween. Use `hideHeader: true` in the artifact properties to suppress the task header.

### Prop values can contain components
`processValue` in renderNode recognizes objects with a `component` key and renders them as React elements. Example: `{"component": {"type": "StatusIndicator", "props": {"type": "success"}, "children": ["Done"]}}` inside a prop will render as a StatusIndicator. Useful for KeyValuePairs `value` props.

### Unknown types fall back to raw HTML
If `type` is not in the Cloudscape component map, it renders as a raw HTML element. So `{"type": "div"}`, `{"type": "br"}`, `{"type": "hr"}` work. Void elements (`br`, `hr`, `img`, etc.) are rendered without children. This is generally not recommended -- use Cloudscape components instead.

### Schema restricts props with additionalProperties: false
The JSON schema uses `additionalProperties: false` on some components. Key restrictions:
- **Header**: Only `variant`, `description`, `counter` allowed. `info`, `actions` rejected.
- **Button**: Only `variant`, `iconName`, `iconAlign`, `href`, `target` allowed. `disabled`, `loading` rejected.
- **FileUpload**: Only `multiple`, `showFileLastModified`, `showFileSize`, `accept`, `constraintText`, `errorText`, `warningText` allowed.

Props not in the schema will fail validation even if the Cloudscape component supports them.

## What Works Well

These patterns are reliable and cover the majority of HITL use cases:

- Display dashboards: StatusIndicator, KeyValuePairs, PieChart, ProgressBar, Badge
- Data tables: Table with automatic pagination, filtering, sorting, expandable rows, component cells
- Text input forms: Input + Textarea + RadioGroup + FileUpload with fieldId
- Rich text: Markdown with code blocks, syntax highlighting, GFM tables, links
- Informational layouts: Alert, Header, Box, SpaceBetween, ColumnLayout, Grid, Tabs, ExpandableSection
- Mixed layouts: combining display components and input components in one view

Estimated coverage: 60-70% of HITL use cases (review a plan, provide feedback, upload a file, make a single choice, view a dashboard).
