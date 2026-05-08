# HITL UI — Validation, Testing & LLM Prompts

## JSON Validation

### What Gets Validated

1. **Component types** — Must be in the ~53-component schema enum
2. **Required props** — `fieldId` on inputs (only Input, Textarea, RadioGroup, FileUpload capture input), `columnDefinitions`+`items` on Table, `markdownText` on Markdown, `data` on PieChart
3. **No submit buttons** — Buttons with Submit/Cancel/Save/OK/Close text rejected
4. **No Container** — Container is banned (ESLint `no-container-component`). Use SpaceBetween + Header instead.
5. **Table variant** — Table must have `variant: "borderless"` (ESLint `require-table-borderless-variant`)
6. **Layout children** — SpaceBetween, ColumnLayout, Grid, Cards, Tabs, Form can only have component children, never raw text
7. **JSON booleans** — `true`/`false`, not `"True"`/`"False"`
8. **`"type"` field** — Not `"component"` or `"component_type"`

### Common Errors and Fixes

**WRONG: 1. Missing fieldId:**
```json
WRONG: { "type": "Input", "props": { "placeholder": "Name" } }
CORRECT: { "type": "Input", "props": { "fieldId": "userName", "placeholder": "Name" } }
```
**Why:** Without fieldId, responses get auto-generated IDs like `:r1:` that are impossible to map back.

**WRONG: 2. Raw text in layout component:**
```json
WRONG: { "type": "SpaceBetween", "children": ["Hello"] }
CORRECT: { "type": "SpaceBetween", "children": [{ "type": "Box", "children": ["Hello"] }] }
```
**Why:** SpaceBetween, Container, ColumnLayout, Grid, Cards, Tabs, Form are layout components that arrange child components — they can't render text directly.

**WRONG: 3. Submit button included:**
```json
WRONG: { "type": "Button", "props": { "variant": "primary" }, "children": ["Submit"] }
CORRECT: (remove it entirely — platform handles submission)
```
**Why:** The platform auto-injects submit/save/reject buttons. Including your own creates duplicates.

**WRONG: 4. Python-style booleans:**
```json
WRONG: { "type": "Toggle", "props": { "checked": "True" } }
CORRECT: { "type": "Toggle", "props": { "checked": true } }
```
**Why:** `"True"` is a string, not a boolean. Causes type coercion errors.

**WRONG: 5. Wrong type field:**
```json
WRONG: { "component": "Button", "props": {} }
CORRECT: { "type": "Button", "props": {} }
```
**Why:** Schema requires `"type"`. Using `"component"` causes validation failure.

**WRONG: 6. Placeholder data when real data provided:**
```json
WRONG: User says "45 healthy, 12 warning" → { "data": [{ "title": "A", "value": 100 }] }
CORRECT: { "data": [{ "title": "Healthy", "value": 45 }, { "title": "Warning", "value": 12 }] }
```
**Why:** Use the exact values the user provides. Don't substitute with generic data.

## Testing in Storybook

1. Copy generated JSON
2. Open: `https://assets.transform-alpha-intg.us-west-2.on.aws/storybook/index.html?path=/story/components-hitlenginerenderer--playground&globals=locale:en`
3. Paste into input area → see rendered UI
4. Test interactions (type in fields, upload files, select options)
5. Iterate as needed

The playground has example templates (Simple, Pie Chart, Table, Dashboard) and tabs showing the LLM instruction variants.

## Deploying as Agent Artifact

**For HITL Tasks:**
```json
{
  "properties": {
    "domTreeJson": { ... your JSON ... },
    "hideHeader": false
  }
}
```
1. Save artifact → get `artifactId`
2. Create HITL task with `uxComponentId: "DynamicHITLRenderEngine"` and `artifactId`
3. Platform renders, manages buttons, captures input
4. Agent retrieves human artifact with responses keyed by `fieldId`

**Metadata behavior:**
- Completed tasks / terminal jobs → all inputs disabled
- CRITICAL severity → submit sends for approval
- NON_BLOCKING → transformation continues while awaiting input

**For Dashboards:** Pass JSON directly as `domTreeJson` — no wrapper needed.

## LLM Prompt Variants

Three prompt variants exist for generating HITL UI JSON with external LLMs:

| Variant | Size | Best For |
|---------|------|----------|
| Base | ~8K tokens | Complex UIs, first-time generation |
| Optimized | ~5K tokens | Simple UIs, experienced users |
| Opus4 | ~6K tokens | Claude Opus 4 specifically |

**Source files:**
```
TransformUIComponents/src/DynamicHITLRenderEngine/
├── DynamicHITLRenderEngine.llm-instructions.md           # Base
├── DynamicHITLRenderEngine.llm-instructions.optimized.md # Optimized
└── DynamicHITLRenderEngine.llm-instructions.opus4.md     # Opus4
```

### Using with External LLMs

**Option A: Kiro generates directly** — Just describe what you need.

**Option B: External LLM** — Copy a prompt variant, paste into ChatGPT/Claude/Bedrock, add your request, copy JSON back, ask me to validate.

### Key Rules from the Prompts

1. NEVER generate submit/cancel/save buttons
2. NEVER put raw text in layout components
3. ALWAYS use `fieldId` on inputs (Input, Textarea, RadioGroup, FileUpload)
4. ALWAYS use `"type"` field
5. ALWAYS return pure JSON
6. ALWAYS use JSON booleans

### Component Selection Guide

| Data Type | Component |
|-----------|-----------|
| Single status | StatusIndicator |
| Proportional data (2-7 categories) | PieChart |
| Comparison across categories | BarChart |
| Trend over time | LineChart |
| Structured rows/columns | Table |
| Key-value metadata | KeyValuePairs |
| Rich formatted text | Markdown |
| Important message | Alert |
| Progress | ProgressBar |
| Loading placeholder | ContentLoader |

### Tips for Best Results

- Be specific: "form with email and phone inputs" not "create a form"
- Provide data: "pie chart with 45 healthy, 12 warning, 3 critical"
- Mention constraints: "file upload for .zip only, max 10MB"
- Specify layout: "3-column grid with metrics"

## Searching HITL UI Documentation

Use the MCP search tools to find HITL UI information:

```
keyword_search("HITL UI JSON schema")
search_by_source("wrapped components", "hitl-ui-quip")
search_by_source("rendering engine", "hitl-ui-wiki")
```

Available HITL sources for `search_by_source`: `hitl-ui-quip`, `hitl-ui-wiki`, `hitl-getting-started`, `hitl-component-library`, `hitl-common-patterns`, `hitl-validation`
