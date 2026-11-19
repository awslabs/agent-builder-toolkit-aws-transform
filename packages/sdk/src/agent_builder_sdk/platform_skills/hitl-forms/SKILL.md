---
name: hitl-forms
description: Use when composing the form a human will fill in for a HITL task - choosing field types, validation, and layout for create_autoform_hitl_task. Field-type mistakes lose user input silently, so load this before building any non-trivial form.
---

# Authoring HITL Forms

`create_autoform_hitl_task(args=..., step_id=..., title=..., description=...)` renders a
form from a declarative schema. The schema is static — what you send is exactly what the
user sees, and only certain field types capture input.

## Field types

| type | Captures input? | Use for |
|---|---|---|
| `text` | yes | short values (ARNs, names, regions); `variant: number` for numerics |
| `textarea` | yes | free-form text |
| `select` | yes | one choice from a list |
| `radiogroup` | yes | one choice, all options visible |
| `multiselect` | yes | several choices |
| `checkbox` | yes | a boolean |
| `fileUploadV2` | yes | user-provided files |
| `jsonBlock` | yes | a JSON value the user edits (validates JSON on submit) |
| `infocontainer` | NO — display only | key/value context you show the user |

Rules that prevent silent input loss:

- **Every field needs a unique `name`.** The submission is keyed by it; a duplicate or
  missing name means you cannot read the answer back.
- **`infocontainer` is the only display-only type — it never returns data.** When you need
  the user to confirm displayed content, add a real input field beside it (e.g. a radiogroup
  "Approve / Request changes"). Every other type above captures input, including `jsonBlock`.
- **Mark fields `required: true`** when the next step cannot proceed without them —
  otherwise expect empty answers and validate after reading.
- **Validate at the field, not after.** `text`/`textarea` accept a `validation` object
  (`pattern`, `minLength`, `maxLength`, `errorMessage`). A regex on an ARN field catches
  a typo at submit time; validating after SUBMITTED costs a whole extra round-trip with
  the human.
- **The platform owns the buttons.** Submit/save/cancel are rendered by the platform; do
  not model buttons as fields or instruct the user to "click OK".
- **No conditional logic.** Fields cannot appear/disappear based on other answers. If the
  flow branches, split it into chained tasks (see hitl-loop: `CLOSED_PENDING_NEXT_TASK`).

## Design guidance

- One task = one coherent ask. Ten related fields in one form beat four sequential
  one-field tasks; unrelated asks go in separate tasks.
- Label in the user's vocabulary ("S3 bucket where your Parquet files live"), never in
  platform or tool vocabulary.
- Prefill what you already know via `placeholder`/defaults instead of making the user
  re-type it.
- For "pick from things I found" (tables, schemas, buckets), prefer
  `create_autotable_hitl_task` over a giant radiogroup.

## Reading the answer

After SUBMITTED, `retrieve_hitl_output_as_string(hitl_task_id)` returns the submission;
answers are keyed by field `name`. Parse defensively: optional fields may be absent, and
file uploads arrive as references you download via the artifact tools, not inline bytes.
