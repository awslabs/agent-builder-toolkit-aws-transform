# HITL Task Shapes

Per-variant behavior. Read this when chaining tasks or parsing an answer you have
just received.

## Chaining a follow-up

Chain only when the follow-up continues the same exchange — refining or drilling into the answer
you just got. An unrelated new ask is a new task, not a chained one.

```
read the first task's output
close_hitl_task(first_id, closure_type="CLOSED_PENDING_NEXT_TASK")
create the follow-up
start_hitl_task(second_id, first_in_chain=False)
```

`first_in_chain=False` changes where the task lands: it starts in `IN_PROGRESS` instead of
`AWAITING_HUMAN_INPUT`, and the user sees a continuing conversation rather than a fresh unopened
request. **Adjust your poll: a chained task never passes through `AWAITING_HUMAN_INPUT`**, so
waiting for that status hangs. Wait for the answer instead.

Closing the first task as plain `CLOSED` breaks the continuity the user sees — use
`CLOSED_PENDING_NEXT_TASK`.


## Read the answer according to its component

Branch before consuming `retrieve_hitl_output_as_string`:

- **File upload task (`FileUploadComponent` only)** — the retriever keys off `uxComponentId ==
  "FileUploadComponent"`: it parses the JSON and base64-decodes each uploaded file, so you get
  back a dict with decoded content inline. Do not call `json.loads` on it. This is the only case
  that returns inline bytes — a `fileUploadV2` file *field* inside an autoform (and a standalone
  `FileUploadV2` task) does not; it falls under the next bullet and arrives as artifact
  references (see `hitl-forms` / `artifact-io`).
- **Every other component (autoform, autotable, custom)** — the payload is a raw string. Parse it
  yourself; answers are keyed by the field `name` you set (see `hitl-forms`).

Assuming one shape for both leaves autoform answers as an unparsed string that you then
pattern-match instead of reading properly.

## Severity is frozen at creation

You cannot raise or otherwise change severity after creation.

If you realize mid-interaction that a `STANDARD` task should have been a `CRITICAL` approval gate,
close the old task and create a new `CRITICAL` one. Do not try to escalate in place.

## `AWAITING_APPROVAL` is not a status your tasks reach

Never write poll logic waiting for `AWAITING_APPROVAL`. It is produced only for
TOOL_APPROVAL-category tasks, and your creation surface has no category parameter — so every task
you create lands in `AWAITING_HUMAN_INPUT` or `IN_PROGRESS`. Note that `CRITICAL` severity does
**not** imply approval category.

If a task you are polling shows `AWAITING_APPROVAL`, it was not created by you — do not close it.
