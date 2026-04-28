# HITL System Architecture

## Three Participants

Every HITL interaction involves three participants:
- **Agent** — creates tasks, uploads artifacts, polls for responses, processes results. Calls the Agentic API.
- **Human** — views UI in the ATX web app, provides input, submits responses. Interacts via the web app (FES).
- **Platform** — manages task lifecycle, artifact storage (private/public S3 buckets), state transitions, notifications. Runs the HITL Service.

## Two API Surfaces

Agents do NOT call the HITL Service directly. They call the Agentic API, which routes to the HITL Service.

### Agent-Facing (via Agentic API — boto3 `elasticgumbyagenticservice`)
| Operation | What it does |
|-----------|-------------|
| CreateHitlTask | Creates task in CREATED status. Agent artifact stays in private bucket. |
| StartHitlTask | Copies artifact from private to public bucket. Status → AWAITING_HUMAN_INPUT. |
| GetHitlTask | Returns task status and artifacts. Used for polling. |
| CloseHitlTask | Closes task. Default closure type is CANCELLED if not specified. |

### Human-Facing (via FES/Web App)
| Operation | What it does |
|-----------|-------------|
| UpdateHitlTask | Web app calls when human saves progress or sends for approval. Has `PostUpdateAction`: SEND_FOR_APPROVAL (for CRITICAL tasks) or TRANSIT_TO_IN_PROGRESS. |
| SubmitHitlTask | Web app calls when human clicks Submit. Has `action`: APPROVE or REJECT (for CRITICAL tasks). APPROVE → SUBMITTED. REJECT → IN_PROGRESS (task goes back for rework). |
| ListHitlTasks | Lists tasks for a job. Filters are mutually exclusive: only ONE of blockingType, planStepId, tag, agentInstanceId per query. taskStatuses can combine with any filter. |
| GetHitlTask | Also available to web app for displaying task details. |

**Key rule:** Agents should NEVER call UpdateHitlTask or SubmitHitlTask. Those are called by the web app on behalf of the human.

## Complete Task Lifecycle

### Blocking vs Non-Blocking

- **BLOCKING** (default) — Agent pauses and waits for human input before continuing. The transformation job halts until the human submits.
- **NON_BLOCKING** — Agent continues the transformation while awaiting human feedback. The task appears as optional in the job plan.

```
Agent calls CreateHitlTask
    ↓
CREATED (artifact in private bucket)
    ↓
Agent calls StartHitlTask (copies artifact private → public bucket)
    ↓
    ├── firstInChain=true (default) → AWAITING_HUMAN_INPUT (UI visible to human)
    │       ↓
    │   Human opens task → IN_PROGRESS (UpdateHitlTask with TRANSIT_TO_IN_PROGRESS)
    │
    └── firstInChain=false (refresh/chain) → IN_PROGRESS directly (human already engaged)
            ↓
Human fills in form / uploads files / makes selections
    ↓
[If STANDARD severity] → Human submits → SUBMITTED
    ↓
[If CRITICAL severity] → AWAITING_APPROVAL (UpdateHitlTask with SEND_FOR_APPROVAL)
    ↓                        ├── Admin APPROVE → SUBMITTED
    ↓                        └── Admin REJECT → IN_PROGRESS (back to human for rework)
    ↓
SUBMITTED (human artifact available to agent)
    ↓
Agent downloads human artifact, processes response
    ↓
Agent calls CloseHitlTask
    ↓
CLOSED (normal) or CLOSED_PENDING_NEXT_TASK (refresh loop) or CANCELLED

[For Dashboard tasks: CREATED → ... → DELIVERED (artifact delivered, read-only, no human input)]
```

**Important timing:** There is a delay between CREATED and AWAITING_HUMAN_INPUT because StartHitlTask copies the artifact from the private bucket to the public bucket. The agent should not expect instant availability.

**DELIVERED status:** Used only for Dashboard tasks (`HitlTaskType.DASHBOARD`). The artifact is delivered for display but no human input is captured and no worklogs are published.

## Artifact Flow

Two separate artifacts exist for each HITL task:

### Agent Artifact (agent → human)
1. Agent builds UI JSON (domTreeJson or domain-specific schema)
2. Agent wraps in `{"properties": {...}}` (or uses `serialize()` from SDK)
3. Agent uploads to artifact store → gets `artifactId` (stored in private bucket)
4. Agent creates task with `agentArtifact: {artifactId: "..."}`
5. StartHitlTask copies artifact to public bucket
6. Web app renders the artifact as UI

### Human Artifact (human → agent)
1. Human interacts with UI (fills fields, uploads files, selects options)
2. Input values captured by fieldId: `{"fieldId1": value1, "fieldId2": value2}`
3. Human clicks Submit → web app calls SubmitHitlTask with `humanArtifact: {artifactId: "..."}`
4. Human artifact stored in private bucket
5. Agent downloads via `CreateArtifactDownloadUrl` → presigned S3 URL
6. Agent deserializes: `data, should_refresh = deserialize(content)`

### The QT_REFRESH Flag
When the human clicks "Request Changes" instead of "Submit", the human artifact includes `{"QT_REFRESH": true}`. The agent should:
1. Close the current task with `CLOSED_PENDING_NEXT_TASK`
2. Create a new task with updated artifact based on the human's feedback
3. Set `firstInChain=false` on the new StartHitlTask

## Component Registry (90+ Components)

The `uxComponentId` in CreateHitlTask maps to a registered UI component. There are two categories:

### Dynamic Components (agent builds custom UI)
- `DynamicHITLRenderEngine` — renders arbitrary CloudScape UI from domTreeJson. Supports 62+ CloudScape component types. Agent has full control over layout.

### Domain-Specific Components (pre-built UI)
These have fixed UI layouts with schema-defined input/output:

| uxComponentId | Purpose | Schema |
|--------------|---------|--------|
| AutoForm | Auto-generated form from schema | AutoForm.schema.json |
| FileUploadComponent | Simple file upload | FileUploadComponent.schema.json |
| FileUploadV2 | Enhanced file upload with progress | FileUploadV2.schema.json |
| TextInput | Single text input | TextInput.schema.json |
| TableComponent | Data table display | TableComponent.schema.json |
| SelectDropdownComponent | Dropdown selection | selectDropdownComponent.schema.json |
| MarkdownRendererComponent | Markdown display | MarkdownRendererComponent.schema.json |
| FeedbackInput | Text feedback collection | feedbackInput.schema.json |
| FeedbackRating | Star rating | feedbackRating.schema.json |
| FileDownload | File download link | fileDownload.schema.json |
| InformationalMessageComponent | Info display | informationalMessageComponent.schema.json |
| GeneralConnector | Connector setup | GeneralConnector.schema.json |

**When to use which:**
- Use `DynamicHITLRenderEngine` when you need custom UI layout
- Use domain-specific components when a pre-built UI matches your need (simpler, less code)
- Use `AutoForm` when you want a form auto-generated from a JSON schema

## DynamicHITLRenderEngine Rendering Pipeline

### Creating a Dynamic HITL UI (Step by Step)

1. Create domTreeJson following the CloudScape component schema (every input component needs `fieldId`)
2. Validate JSON against schema
3. Test in Storybook playground
4. Wrap JSON in `{"properties": {"domTreeJson": {...}}}` (or use `serialize()` from SDK)
5. Upload as artifact → get `artifactId`
6. Create HITL task with `uxComponentId: "DynamicHITLRenderEngine"` and the `artifactId`
7. Platform renders using the rendering engine, auto-manages submit/save/reject buttons

### How the Rendering Engine Works

When `uxComponentId="DynamicHITLRenderEngine"`:

1. Web app loads the agent artifact's `domTreeJson`
2. `DynamicHITLRenderEngine` component recursively renders the JSON tree
3. Each `type` maps to a React component:
   - CloudScape components (Button, Alert, Header, etc.) → used directly
   - Input components (Input, Textarea, RadioGroup, FileUpload) → wrapped versions that capture values via `useFieldInput(fieldId)`
   - Special components (Table, PieChart, Markdown, ContentLoader) → custom wrappers
4. `HITLCallbackContext` provides:
   - `updateInput(fieldId, value)` — captures input values keyed by fieldId
   - `disabled` state — true when task is completed/submitted or job is terminal
   - `onRefresh` — triggers QT_REFRESH flow
   - Button state management (submit/save/reject visibility and enabled state)
5. When human submits, all captured `{fieldId: value}` pairs become the human artifact

### Wrapped Components in the Rendering Engine

These are CloudScape components with additional logic for input capture and platform integration:

| Wrapper | Base Component | What It Adds |
|---------|---------------|-------------|
| TextInput | Input | Captures value via `useFieldInput(fieldId)`, merges disabled state from context |
| TextArea | Textarea | Same input capture pattern |
| RenderFileUpload | FileUpload | Base64 conversion of uploaded files, file metadata extraction |
| RadioGroupComponent | RadioGroup | Auto-selects first item, captures selected value |
| TableWithRenderer | Table | Filtering, pagination, JSON cell rendering (renders component objects inside table cells) |
| WrappedPieChart | PieChart | i18n support for labels |
| WrappedMarkdown | Markdown | GFM support, syntax highlighting, deeplink rendering |
| ContentLoaderWrapper | ContentLoader | Skeleton loading animation placeholder |

### Wrapped Component Pattern

Every wrapped input component follows this pattern:

```typescript
import { useFieldInput } from '../HITLCallbackContext';

interface MyInputProps {
  fieldId?: string;  // Critical — responses keyed by this value
  // ... other props
}

export const MyInput = (props) => {
  const { handleValueChange, disabled } = useFieldInput(fieldId);
  // On user input: handleValueChange(newValue)
  // disabled = true when task completed/submitted or job terminal
};
```

Key: `useFieldInput(fieldId)` returns `handleValueChange` (to report values to context) and `disabled` (from task/job status). Without `fieldId`, a generated ID like `:r1:` is used — making the response unmappable.

### Disabled State

All inputs are automatically disabled when:
- Task status is CLOSED, SUBMITTED, CANCELLED, or CLOSED_PENDING_NEXT_TASK
- Job status is terminal (COMPLETED, FAILED, STOPPED)

The agent cannot control this — it's enforced by the platform.

### Table Special Handling

Tables receive special treatment because their column definitions require function callbacks for rendering. The rendering engine delegates this to the frontend — the LLM only provides `columnDefinitions` (header + field name) and `items` (data rows). The `TableWithRenderer` wrapper handles sorting, filtering, pagination, and rendering component objects inside cells.

### Security: Declarative-Only Architecture

The system enforces purely declarative JSON. The rendering engine:
- Rejects arbitrary JavaScript in JSON
- Does not execute function callbacks from LLM output
- Delegates all business logic and state management to the frontend
- Validates JSON against schema before rendering

### Source Code References

| Component | Package Path |
|-----------|-------------|
| Rendering Engine | `ElasticGumbyUIComponents/src/DynamicHITLRenderEngine/DynamicHITLRenderEngine.tsx` |
| HITL Context | `ElasticGumbyUIComponents/src/DynamicHITLRenderEngine/HITLCallbackContext.tsx` |
| Wrapped Components (Atoms) | `ElasticGumbyUIComponents/src/DynamicHITLRenderEngine/Atoms/` |
| Component Registry | `ElasticGumbyUIComponents/src/componentRegistry.ts` |
| Schema Registry | `ElasticGumbyUIComponents/schemaRegistry/` |
| Storybook Playground | `https://assets.transform-alpha-intg.us-west-2.on.aws/storybook/index.html?path=/story/components-hitlenginerenderer--playground` |

## CRITICAL Severity Approval Workflow

For `severity=CRITICAL`:
1. Agent creates task with `severity: "CRITICAL"`
2. Human fills in the form
3. Human clicks "Send for Approval" (not Submit) → web app calls UpdateHitlTask with `postUpdateAction: SEND_FOR_APPROVAL`
4. Status → AWAITING_APPROVAL
5. Admin/Approver reviews → calls SubmitHitlTask with `action: APPROVE` or `action: REJECT`
6. If APPROVE → status → SUBMITTED, agent can proceed
7. If REJECT → status → IN_PROGRESS (task goes back to human for rework, NOT to SUBMITTED)

**Key difference from STANDARD:** STANDARD tasks go directly from IN_PROGRESS → SUBMITTED. CRITICAL tasks go IN_PROGRESS → AWAITING_APPROVAL → SUBMITTED (if approved) or back to IN_PROGRESS (if rejected).

## CloseHitlTask Default Gotcha

From the Smithy model: `@default("CANCELLED") closeType: ClosureType`

If you call CloseHitlTask without specifying `closeType`, it defaults to **CANCELLED**, not CLOSED. Always specify the closure type explicitly:
- `CLOSED` — task completed normally
- `CLOSED_PENDING_NEXT_TASK` — refresh loop, another task follows
- `CANCELLED` — task was cancelled (the default if omitted)

The HITL SDK always requires explicit closure type, preventing this gotcha.
