# Adding HITL to Your Agent

## What is HITL Integration?

When your agent needs human input — reviewing plans, confirming configurations, uploading files — it creates a **HITL task**. The agent pauses, the platform renders a UI for the human, and the agent resumes once the human responds. The **HITL SDK** handles the entire lifecycle.

## Prerequisites

- Python 3.11+
- boto3 client for `awstransformagenticservice`
- AWS credentials with Bedrock access

## HITL Task Lifecycle

```
CREATED → AWAITING_HUMAN_INPUT → IN_PROGRESS → SUBMITTED → CLOSED
                                                         ↘ CLOSED_PENDING_NEXT_TASK
```

| Status | Description |
|--------|-------------|
| CREATED | Task created but not yet started |
| AWAITING_HUMAN_INPUT | Task started, waiting for human to begin |
| IN_PROGRESS | Human is actively working on the task |
| SUBMITTED | Human has submitted their response |
| CLOSED | Task completed normally |
| CLOSED_PENDING_NEXT_TASK | Task completed, another task follows (refresh loop) |
| CANCELLED | Agent cancelled the task |
| DELIVERED | Dashboard HITL task artifact delivered |
| AWAITING_APPROVAL | Critical task waiting for admin approval |

## Two Use Cases

### HITL Task (Interactive — Captures User Input)

Agent needs human input. Platform renders JSON with full interactivity, manages submit/save/reject buttons, captures responses.

**Agent artifact structure:**
```json
{
  "properties": {
    "domTreeJson": {
      "type": "SpaceBetween",
      "props": { "direction": "vertical", "size": "l" },
      "children": [ ... ]
    }
  }
}
```

**To hide the task header:** Set `"hideHeader": true` in `properties`.

**Metadata affecting rendering:**
- `HITLTask.status` — Completed tasks disable all inputs
- `HITLTask.severity` — CRITICAL requires approval workflow
- `HITLTask.blockingType` — BLOCKING halts transformation; NON_BLOCKING continues
- `job.status` — Terminal jobs disable all inputs

### Dashboard Display (Read-Only)

Agent shows data. No input capture, no buttons. Pass `domTreeJson` directly (no `properties` wrapper). Use `HitlTaskType.DASHBOARD`.

## The HITL SDK

The SDK has three layers:

1. **Type-safe models** — Pydantic models for 90+ UX components (`TextInput`, `GeneralConnector`, `FileUpload`, etc.)
2. **Serialization utilities** — `serialize()` wraps models in `{"properties": {...}}`, `deserialize()` parses human responses
3. **HitlClient lifecycle management** — Handles artifact upload, task creation, polling, timeout, and refresh loops

| | Without SDK | With SDK |
|---|---|---|
| Build artifact | Manual JSON construction, schema lookup | `TextInput(label="Name", value="")` |
| Wrap for render engine | `json.dumps({"properties": {...}})` | `serialize(artifact)` — automatic |
| Upload to S3 | SHA256 digest + presigned URL + PUT + complete (4 API calls) | `client.upload_artifact(content, ...)` — one call |
| Create + start task | `create_hitl_task()` then `start_hitl_task()` (2 API calls) | `client.create_and_start_task(...)` — one call |
| Poll for response | Manual loop with sleep, timeout, error handling | `client.wait_for_human_submission(task_id)` |
| Refresh loop | Manual create→poll→download→check→close→repeat | `client.execute_with_refresh(...)` |

## Decision Guide: Choosing Your HITL Configuration

| Decision | Options | When to Use |
|----------|---------|-------------|
| Blocking type | `BlockingType.BLOCKING` | Agent must wait for human response before continuing |
| | `BlockingType.NON_BLOCKING` | Agent continues working, checks response later |
| Severity | `Severity.STANDARD` | Normal human input tasks |
| | `Severity.CRITICAL` | Requires approval workflow (admin must approve) |
| Category | `Category.REGULAR` | Standard HITL tasks |
| | `Category.TOOL_APPROVAL` | Tool execution approval |
| Task type | `HitlTaskType.NORMAL` | Interactive task requiring human input |
| | `HitlTaskType.DASHBOARD` | Read-only display, no worklogs published |
| Component | `"DynamicHITLRenderEngine"` | Custom UI built with domTreeJson (search: `keyword_search("HITL getting started domTreeJson")`) |
| | `"TextInput"` | Simple text input |
| | `"FileUploadComponent"` | File upload |
| | `"GeneralConnector"` | Connector setup (see `connector-agent-integration.md`) |
| | (90+ others) | See SDK types for full list |

## Quick Start: One-Shot HITL (5 Steps)

### Step 1: Create Your Client

```python
import os
import boto3
from elastic_gumby_hitl_component_python_sdk import HitlClient, RequestContext

agentic_client = boto3.client("awstransformagenticservice")

request_context = RequestContext(
    job_id=os.environ["JOB_ID"],
    workspace_id=os.environ["WORKSPACE_ID"],
    agent_instance_id=os.environ["AGENT_INSTANCE_ID"],
    authorization_token=os.environ["AUTHORIZATION_TOKEN"],
)
client = HitlClient(agentic_client, request_context)
```

**Key Points:**
- `agentic_client` is your boto3 `awstransformagenticservice` client
- `RequestContext` converts snake_case to camelCase automatically via `.to_dict()`
- Default poll interval: 15s, timeout: 2h. Override in constructor: `HitlClient(agentic_client, request_context, poll_interval_seconds=5, poll_timeout_minutes=60)`

### Step 2: Build Your Artifact Using Type-Safe Models

```python
from elastic_gumby_hitl_component_python_sdk.types import TextInput

artifact = TextInput(label="Review Plan", value="Migration plan details here...")
```

**Key Points:**
- Import component models from `.types` — 90+ available
- Models provide IDE autocomplete and compile-time validation
- No manual JSON construction needed

### Step 3: Upload Artifact

```python
from elastic_gumby_hitl_component_python_sdk import serialize, ArtifactCategoryType, FileType

artifact_id = client.upload_artifact(
    content=serialize(artifact),
    category_type=ArtifactCategoryType.HITL_FROM_AGENT,
    file_type=FileType.JSON,
)
```

**Key Points:**
- `serialize()` wraps in `{"properties": {...}}` automatically
- `upload_artifact()` handles SHA256 digest, presigned URL, S3 PUT, and completion — all in one call
- Returns `artifact_id` string ready for task creation

### Step 4: Create and Start HITL Task

```python
task_id = client.create_and_start_task(
    ux_component_id="TextInput",
    title="Review Migration Plan",
    description="Please review the proposed migration plan",
    hitl_request_artifact={"artifactId": artifact_id},
)
```

**Key Points:**
- `create_and_start_task()` calls both CreateHitlTask AND StartHitlTask
- `ux_component_id` must match the component type you used (e.g., `"TextInput"`, `"DynamicHITLRenderEngine"`)
- Default: `severity=Severity.STANDARD`, `blocking_type=BlockingType.BLOCKING`, `category=Category.REGULAR`
- Optional params: `step_id`, `tag`, `expired_at`, `idempotency_token`

### Step 5: Wait and Process Response

```python
from elastic_gumby_hitl_component_python_sdk import ClosureType, Visibility
from elastic_gumby_hitl_component_python_sdk.util import ArtifactHelper, deserialize

task = client.wait_for_human_submission(task_id)

# Download and deserialize human response
download_response = agentic_client.create_artifact_download_url(
    requestContext=request_context.to_dict(),
    artifactId=task.human_artifact.artifact_id,
    visibility=Visibility.INTERNAL.value,
)
content = ArtifactHelper().download(
    download_response["s3preSignedUrl"],
    download_response["requestHeaders"],
)
data, should_refresh = deserialize(content)

# Close task
client.close_task(task_id, ClosureType.CLOSED)
```

**Key Points:**
- `wait_for_human_submission()` blocks until SUBMITTED status (polls every 15s by default)
- `deserialize()` returns `(data_dict, should_refresh)` — `should_refresh` is True if user clicked "Request Changes"
- Always close the task when done
- `ArtifactHelper` has a 120s default timeout to accommodate large file uploads

## Advanced: Refresh Loop (execute_with_refresh)

When users may request changes, use `execute_with_refresh` to handle the full create→poll→download→check→close-or-repeat cycle automatically:

```python
from elastic_gumby_hitl_component_python_sdk import (
    HitlClient, serialize, ArtifactCategoryType, FileType,
)
from elastic_gumby_hitl_component_python_sdk.types import TextInput


def build_initial_request():
    artifact = TextInput(label="Review Plan", value="Initial migration plan...")
    artifact_id = client.upload_artifact(
        content=serialize(artifact),
        category_type=ArtifactCategoryType.HITL_FROM_AGENT,
        file_type=FileType.JSON,
    )
    return {
        "ux_component_id": "TextInput",
        "title": "Review Migration Plan",
        "description": "Please review the proposed migration plan",
        "hitl_request_artifact": {"artifactId": artifact_id},
    }


def build_refresh_request(previous_response):
    # Update artifact based on human feedback
    feedback = previous_response.get("value", "")
    artifact = TextInput(label="Review Plan (Updated)", value=f"Updated based on: {feedback}")
    artifact_id = client.upload_artifact(
        content=serialize(artifact),
        category_type=ArtifactCategoryType.HITL_FROM_AGENT,
        file_type=FileType.JSON,
    )
    return {
        "ux_component_id": "TextInput",
        "title": "Review Migration Plan (Revised)",
        "description": "Updated plan based on your feedback",
        "hitl_request_artifact": {"artifactId": artifact_id},
    }


response = client.execute_with_refresh(
    initial_request_fn=build_initial_request,
    on_refresh=build_refresh_request,
    max_iterations=10,
)
selected_option = response.get("value")
```

**Key Points:**
- Handles full cycle: create → poll → download → check `QT_REFRESH` → close or repeat
- `max_iterations` prevents infinite loops (default: 10)
- `on_refresh(previous_response)` receives the deserialized human response dict
- Automatically closes with `CLOSED_PENDING_NEXT_TASK` on refresh, `CLOSED` on final iteration
- Sets `first_in_chain=True` for the first task, `False` for subsequent refresh tasks

## Advanced: Dynamic HITL UI (DynamicHITLRenderEngine)

For custom UIs beyond simple text input, use `DynamicHITLRenderEngine` with `domTreeJson`:

```python
from elastic_gumby_hitl_component_python_sdk import serialize, ArtifactCategoryType, FileType
from elastic_gumby_hitl_component_python_sdk.util.json_utils import to_hitl_json

# Build custom UI as a dict (DynamicHITLRenderEngine uses domTreeJson)
ui_json = {
    "domTreeJson": {
        "type": "SpaceBetween",
        "props": {"direction": "vertical", "size": "l"},
        "children": [
            {
                "type": "Header",
                "props": {"variant": "h2"},
                "children": ["Review Configuration"],
            },
            {
                "type": "FormField",
                "props": {"label": "Environment"},
                "children": [
                    {
                        "type": "Select",
                        "props": {
                            "fieldId": "environment",
                            "placeholder": "Choose environment",
                            "options": [
                                {"label": "Production", "value": "prod"},
                                {"label": "Staging", "value": "staging"},
                            ],
                        },
                    }
                ],
            },
        ],
    }
}

# Use to_hitl_json for dict-based artifacts (wraps in {"properties": {...}})
artifact_id = client.upload_artifact(
    content=to_hitl_json(ui_json),
    category_type=ArtifactCategoryType.HITL_FROM_AGENT,
    file_type=FileType.JSON,
)

task_id = client.create_and_start_task(
    ux_component_id="DynamicHITLRenderEngine",
    title="Review Configuration",
    description="Select your target environment",
    hitl_request_artifact={"artifactId": artifact_id},
)
```

**Key Points:**
- Use `to_hitl_json(dict)` for dict-based artifacts, `serialize(model)` for Pydantic models
- `ux_component_id` must be `"DynamicHITLRenderEngine"` for custom UIs
- Search `keyword_search("HITL Q&A workflow domTreeJson")` for the full Q&A workflow to build `domTreeJson`
- Search `keyword_search("HITL common patterns templates")` for 10+ ready-to-use UI templates

## Complete Example: File Upload Review

```python
import os
import boto3
from elastic_gumby_hitl_component_python_sdk import (
    HitlClient, RequestContext, serialize, ArtifactCategoryType, FileType, ClosureType, Visibility,
)
from elastic_gumby_hitl_component_python_sdk.types import TextInput
from elastic_gumby_hitl_component_python_sdk.util import ArtifactHelper, deserialize

# Setup
agentic_client = boto3.client("awstransformagenticservice")
request_context = RequestContext(
    job_id=os.environ["JOB_ID"],
    workspace_id=os.environ["WORKSPACE_ID"],
    agent_instance_id=os.environ["AGENT_INSTANCE_ID"],
    authorization_token=os.environ["AUTHORIZATION_TOKEN"],
)
client = HitlClient(agentic_client, request_context)

# Build and upload artifact
artifact = TextInput(label="Upload Config", value="Please upload your configuration file")
artifact_id = client.upload_artifact(
    content=serialize(artifact),
    category_type=ArtifactCategoryType.HITL_FROM_AGENT,
    file_type=FileType.JSON,
)

# Create and start task
task_id = client.create_and_start_task(
    ux_component_id="TextInput",
    title="Upload Configuration File",
    description="Please upload the missing configuration file",
    hitl_request_artifact={"artifactId": artifact_id},
)

# Wait for human response
task = client.wait_for_human_submission(task_id)

# Download and process response
download_response = agentic_client.create_artifact_download_url(
    requestContext=request_context.to_dict(),
    artifactId=task.human_artifact.artifact_id,
    visibility=Visibility.INTERNAL.value,
)
content = ArtifactHelper().download(
    download_response["s3preSignedUrl"],
    download_response["requestHeaders"],
)
data, should_refresh = deserialize(content)

# Handle refresh or close
if should_refresh:
    client.close_task(task_id, ClosureType.CLOSED_PENDING_NEXT_TASK)
    # Create follow-up task with updated artifact...
else:
    client.close_task(task_id, ClosureType.CLOSED)
    # Process data...
    user_input = data.get("value", "")
```

## Complete Example: Approval with Refresh Loop

```python
import os
import boto3
from elastic_gumby_hitl_component_python_sdk import (
    HitlClient, RequestContext, serialize, ArtifactCategoryType, FileType,
)
from elastic_gumby_hitl_component_python_sdk.types import TextInput
from elastic_gumby_hitl_component_python_sdk.util.json_utils import to_hitl_json

# Setup
agentic_client = boto3.client("awstransformagenticservice")
request_context = RequestContext(
    job_id=os.environ["JOB_ID"],
    workspace_id=os.environ["WORKSPACE_ID"],
    agent_instance_id=os.environ["AGENT_INSTANCE_ID"],
    authorization_token=os.environ["AUTHORIZATION_TOKEN"],
)
client = HitlClient(agentic_client, request_context)

plan_content = "1. Migrate database\n2. Update API endpoints\n3. Run integration tests"


def build_initial_request():
    ui = {
        "domTreeJson": {
            "type": "SpaceBetween",
            "props": {"direction": "vertical", "size": "l"},
            "children": [
                {"type": "Header", "props": {"variant": "h2"}, "children": ["Approve Migration Plan"]},
                {"type": "Alert", "props": {"type": "info"}, "children": [plan_content]},
                {
                    "type": "FormField",
                    "props": {"label": "Decision"},
                    "children": [
                        {
                            "type": "RadioGroup",
                            "props": {
                                "fieldId": "decision",
                                "items": [
                                    {"value": "approve", "label": "Approve"},
                                    {"value": "reject", "label": "Reject"},
                                ],
                            },
                        }
                    ],
                },
                {
                    "type": "FormField",
                    "props": {"label": "Comments"},
                    "children": [
                        {"type": "Textarea", "props": {"fieldId": "comments", "rows": 4}}
                    ],
                },
            ],
        }
    }
    artifact_id = client.upload_artifact(
        content=to_hitl_json(ui),
        category_type=ArtifactCategoryType.HITL_FROM_AGENT,
        file_type=FileType.JSON,
    )
    return {
        "ux_component_id": "DynamicHITLRenderEngine",
        "title": "Approve Migration Plan",
        "description": "Review and approve the migration plan",
        "hitl_request_artifact": {"artifactId": artifact_id},
    }


def build_refresh_request(previous_response):
    feedback = previous_response.get("comments", "No feedback provided")
    updated_plan = f"{plan_content}\n\n--- Updated based on feedback ---\n{feedback}"
    ui = {
        "domTreeJson": {
            "type": "SpaceBetween",
            "props": {"direction": "vertical", "size": "l"},
            "children": [
                {"type": "Header", "props": {"variant": "h2"}, "children": ["Approve Migration Plan (Revised)"]},
                {"type": "Alert", "props": {"type": "info"}, "children": [updated_plan]},
                {
                    "type": "FormField",
                    "props": {"label": "Decision"},
                    "children": [
                        {
                            "type": "RadioGroup",
                            "props": {
                                "fieldId": "decision",
                                "items": [
                                    {"value": "approve", "label": "Approve"},
                                    {"value": "reject", "label": "Reject"},
                                ],
                            },
                        }
                    ],
                },
                {
                    "type": "FormField",
                    "props": {"label": "Comments"},
                    "children": [
                        {"type": "Textarea", "props": {"fieldId": "comments", "rows": 4}}
                    ],
                },
            ],
        }
    }
    artifact_id = client.upload_artifact(
        content=to_hitl_json(ui),
        category_type=ArtifactCategoryType.HITL_FROM_AGENT,
        file_type=FileType.JSON,
    )
    return {
        "ux_component_id": "DynamicHITLRenderEngine",
        "title": "Approve Migration Plan (Revised)",
        "description": "Updated plan based on your feedback",
        "hitl_request_artifact": {"artifactId": artifact_id},
    }


response = client.execute_with_refresh(
    initial_request_fn=build_initial_request,
    on_refresh=build_refresh_request,
    max_iterations=5,
)
decision = response.get("decision")
comments = response.get("comments", "")
```

## Critical Rules

1. **ALWAYS use the HITL SDK** — Do not manually construct `{"properties": {...}}` JSON. Use `serialize()` for Pydantic models or `to_hitl_json()` for dicts.
2. **ALWAYS close tasks** — Use `client.close_task()` with appropriate `ClosureType`. Unclosed tasks leak resources and block the job plan.
3. **ALWAYS check `should_refresh`** — If True, close with `ClosureType.CLOSED_PENDING_NEXT_TASK` and create a follow-up task.
4. **NEVER skip `start_hitl_task`** — `create_and_start_task()` handles this. If calling raw APIs, you must call both create AND start.
5. **NEVER hardcode request context** — Use environment variables or the `RequestContext` dataclass.
6. **Use `ArtifactCategoryType.HITL_FROM_AGENT`** for agent→human artifacts, `HITL_FROM_USER` for human→agent.
7. **Set `first_in_chain=False` for refresh iterations** — `create_and_start_task()` defaults to `first_in_chain=True`. In a manual refresh loop, set it to `False` after the first task. `execute_with_refresh()` handles this automatically.
8. **Match `ux_component_id` to the artifact type** — `TextInput` model → `ux_component_id="TextInput"`. `domTreeJson` dict → `ux_component_id="DynamicHITLRenderEngine"`. Mismatches cause render failures.

## Common Errors and Fixes

WRONG: **Manual JSON wrapping:**
```python
json_str = json.dumps({"properties": {"label": "Name", "value": ""}})
```
CORRECT: **Use serialize():**
```python
from elastic_gumby_hitl_component_python_sdk import serialize
from elastic_gumby_hitl_component_python_sdk.types import TextInput

json_str = serialize(TextInput(label="Name", value=""))
```
**Why:** `serialize()` handles the `{"properties": {...}}` wrapping, excludes None fields, and uses correct alias names.

---

WRONG: **Forgetting to close task:**
```python
task = client.wait_for_human_submission(task_id)
data, _ = deserialize(content)
# ... process data, but never close
```
CORRECT: **Always close:**
```python
client.close_task(task_id, ClosureType.CLOSED)
```
**Why:** Unclosed tasks leak resources and block the job plan.

---

WRONG: **Ignoring QT_REFRESH flag:**
```python
data, _ = deserialize(content)  # Ignoring should_refresh!
```
CORRECT: **Check and handle refresh:**
```python
data, should_refresh = deserialize(content)
if should_refresh:
    client.close_task(task_id, ClosureType.CLOSED_PENDING_NEXT_TASK)
    # Create follow-up task with updated artifact
```
**Why:** User explicitly requested changes. Ignoring it breaks the UX contract.

---

WRONG: **Wrong ux_component_id:**
```python
client.create_and_start_task(ux_component_id="textinput", ...)  # lowercase!
```
CORRECT: **Exact component name:**
```python
client.create_and_start_task(ux_component_id="TextInput", ...)
```
**Why:** Component IDs are case-sensitive and must match the registered component name exactly.

---

WRONG: **Manual SHA256 + presigned URL + S3 PUT:**
```python
digest = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
response = agentic_client.create_artifact_upload_url(...)
requests.put(response["s3preSignedUrl"], data=content, headers=...)
agentic_client.complete_artifact_upload(...)
```
CORRECT: **Use upload_artifact():**
```python
artifact_id = client.upload_artifact(
    content=serialize(artifact),
    category_type=ArtifactCategoryType.HITL_FROM_AGENT,
    file_type=FileType.JSON,
)
```
**Why:** `upload_artifact()` handles SHA256 digest, presigned URL, S3 PUT, and completion in one call.

---

WRONG: **Passing `RequestContext` dataclass to raw boto3 calls:**
```python
agentic_client.create_artifact_download_url(
    requestContext=request_context,  # Dataclass — boto3 can't serialize this
    ...
)
```
CORRECT: **Convert to dict with `.to_dict()`:**
```python
agentic_client.create_artifact_download_url(
    requestContext=request_context.to_dict(),
    ...
)
```
**Why:** boto3 expects a dict with camelCase keys. `HitlClient` methods handle this internally, but direct boto3 calls require `.to_dict()`.


## Input Component Output Types

Each input component returns a different value shape in the human artifact:

| Component | fieldId Required | Output Type |
|-----------|-----------------|-------------|
| Input | Yes | `string` |
| Textarea | Yes | `string` |
| FileUpload | Yes | `{ uploadedFiles: [{ content, name, isZip }] }` |
| RadioGroup | Yes | `string` (selected value, auto-selects first item) |
| Select | Yes | `string` |
| Multiselect | Yes | `string[]` |
| Checkbox | Yes | `boolean` |
| DatePicker | Yes | `string` |
| TimeInput | Yes | `string` |

Example response: `{ "userName": "John", "configFile": { "uploadedFiles": [{ "content": "base64...", "name": "config.yaml", "isZip": false }] } }`

## SpaceBetween Sizing Guide

| Use Case | Direction | Size |
|----------|-----------|------|
| Form fields | vertical | m |
| Content sections | vertical | l |
| Page sections | vertical | xl |
| Inline elements | horizontal | s |

## Guided Q&A Workflow for Building HITL UI

### Phase 0: Use Case
- **HITL Task** (interactive, captures input) or **Dashboard** (read-only display)?

### Phase 1: UI Type
- **Form** (collect input) → Root: SpaceBetween
- **Table** (display data) → Root: Table
- **Dashboard** (metrics/charts) → Root: Container
- **Custom** → Describe it

### Phase 2: Purpose
- What's the main user action?
- Is this blocking or non-blocking?
- Who is the user?

### Phase 3: Components
| Need | Component |
|------|-----------|
| Single-line text | FormField > Input (fieldId required) |
| Multi-line text | FormField > Textarea (fieldId required) |
| File upload | FormField > FileUpload (fieldId required) |
| Selection from options | FormField > RadioGroup or Select (fieldId required) |
| Yes/no choice | Checkbox (fieldId required) |
| Data table | Table (columnDefinitions + items) |
| Status display | StatusIndicator |
| Metrics | KeyValuePairs or PieChart |
| Instructions | Alert or Markdown |
| Section title | Header |

### Phase 4: Generate and Validate
1. Generate JSON based on answers
2. Validate (no submit buttons, fieldId on inputs, no raw text in layouts)
3. Fix any issues
4. Present validated JSON

## Type-Safe Artifact Models

90+ auto-generated Pydantic models. Use instead of manual JSON construction.

```python
from elastic_gumby_hitl_component_python_sdk.types import TextInput, GeneralConnector, Connector, FieldModel

# Simple component
text_input = TextInput(label="Enter name", value="", placeholder="Your name...")

# Connector (type format: owner|shortName|version)
connector = GeneralConnector(
    connector=Connector(
        connectorType="platform|s3|1",
        maxInstances=1,
        fields=[
            FieldModel(fieldName="s3BucketArn", fieldTitle="S3 Bucket ARN", fieldRequired=True),
            FieldModel(fieldName="kmsKeyArn", fieldTitle="KMS Key ARN", fieldRequired=False),
        ]
    )
)
```

## Serialization Utilities

```python
from elastic_gumby_hitl_component_python_sdk import serialize
from elastic_gumby_hitl_component_python_sdk.util import deserialize
```

- **`serialize(artifact)`** — Wraps Pydantic model in `{"properties": {...}}`. Returns JSON string.
- **`deserialize(json_str)`** — Parses human artifact. Returns `(data_dict, should_refresh)`. `should_refresh` is True when user clicked "Request Changes" (`QT_REFRESH` flag).
- **`to_hitl_json(data)`** — Fallback for dicts when no Pydantic model available. Same wrapping as `serialize`.

## Enums Reference

```python
from elastic_gumby_hitl_component_python_sdk import (
    Severity, BlockingType, HitlTaskType, Category, ClosureType,
    ArtifactCategoryType, FileType, Visibility, HitlTaskStatus,
)
```

| Enum | Values |
|------|--------|
| Severity | STANDARD, CRITICAL |
| BlockingType | BLOCKING, NON_BLOCKING |
| HitlTaskType | NORMAL, DASHBOARD |
| Category | REGULAR, TOOL_APPROVAL |
| ClosureType | CLOSED, CLOSED_PENDING_NEXT_TASK, CANCELLED |
| ArtifactCategoryType | AGENT_INPUT, AGENT_OUTPUT, CUSTOMER_INPUT, CUSTOMER_OUTPUT, HITL_FROM_AGENT, HITL_FROM_USER, INTERNAL, STATE, PLAN_STEP_OUTPUT, PLAN_STEP_SUMMARY |
| FileType | ZIP, JSON, PDF, HTML, TXT, MARKDOWN, CSV, PPTX, XLSX, OTHER |
| Visibility | EXTERNAL, INTERNAL |

## Refactoring: Before and After SDK

**Before (manual — ~20 lines, error-prone):**
```python
import json, hashlib, base64, requests, time

json_str = json.dumps({"properties": {"label": "Review", "value": "data"}})
digest = base64.b64encode(hashlib.sha256(json_str.encode()).digest()).decode()
upload_resp = agentic_client.create_artifact_upload_url(
    requestContext=ctx, contentDigest={"sha256": digest},
    artifactReference={"artifactType": {"categoryType": "HITL_FROM_AGENT", "fileType": "JSON"}},
)
requests.put(upload_resp["s3preSignedUrl"], data=json_str, headers=upload_resp["requestHeaders"])
agentic_client.complete_artifact_upload(requestContext=ctx, artifactId=upload_resp["artifactId"])
resp = agentic_client.create_hitl_task(
    requestContext=ctx, uxComponentId="TextInput", title="Review",
    description="Review", hitlRequestArtifact={"artifactId": upload_resp["artifactId"]},
    severity="STANDARD", blockingType="BLOCKING", hitlTaskType="NORMAL", category="REGULAR",
)
agentic_client.start_hitl_task(requestContext=ctx, hitlTaskId=resp["hitlTaskId"], firstInChain=True)
while True:
    task = agentic_client.get_hitl_task(requestContext=ctx, hitlTaskId=resp["hitlTaskId"])
    if task["hitlTask"]["hitlTaskStatus"] == "SUBMITTED":
        break
    time.sleep(15)
```

**After (SDK — ~5 lines, type-safe):**
```python
from elastic_gumby_hitl_component_python_sdk import HitlClient, serialize, ArtifactCategoryType, FileType
from elastic_gumby_hitl_component_python_sdk.types import TextInput

artifact = TextInput(label="Review", value="data")
client = HitlClient(agentic_client, request_context)
artifact_id = client.upload_artifact(content=serialize(artifact), category_type=ArtifactCategoryType.HITL_FROM_AGENT, file_type=FileType.JSON)
task_id = client.create_and_start_task(ux_component_id="TextInput", title="Review", description="Review", hitl_request_artifact={"artifactId": artifact_id})
task = client.wait_for_human_submission(task_id)
```

## Next Steps

- Search `keyword_search("HITL getting started domTreeJson")` for building custom HITL UI JSON with DynamicHITLRenderEngine
- Search `keyword_search("HITL common patterns templates")` for 10+ ready-to-use UI templates
- See `connector-agent-integration.md` for connector-specific HITL integration
- See `orchestrator-patterns.md` for agent setup and runtime architecture
