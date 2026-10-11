---
name: hitl-loop
description: Use whenever you need anything from the human - input, a decision, an approval, or a file. Covers the HITL task lifecycle (create, start, poll, read, close), approval gates before mutating actions, rejection rework, and task chaining. HITL is a strict protocol; skipping a step loses the task or the human's answer.
---

# HITL Task Loop

A HITL task is the only way to get structured input or a recorded decision from the user. The
lifecycle is a strict protocol, and most of it is the platform's work — your job is to create,
start, announce, poll, read, close, in that order.

## The protocol

```
1. step_id  = a platform plan step id            (list_job_plan_steps if unsure)
2. create   = create_hitl_task(...)              -> hitl_task_id   [exists, INVISIBLE]
3. start    = start_hitl_task(hitl_task_id)                        [now visible]
4. tell     = tell the user in chat what you need and why
5. poll     = get_hitl_task(hitl_task_id) until the ANSWER EXISTS  (see below)
6. read     = retrieve_hitl_output_as_string(hitl_task_id)
7. close    = close_hitl_task(hitl_task_id, closure_type="CLOSED")
```

The `create_autoform_hitl_task` and `create_autotable_hitl_task` helpers do steps 2 AND 3 in one call, and return the
`hitl_task_id` plus the status start landed in. Read those off the response and go straight to
step 4 — calling `start_hitl_task` on a helper-created task fails, because start only accepts a
task still in `CREATED`.

## What `start_hitl_task` does for you

One call: verifies the task is still `CREATED`, copies your request artifact from the private to
the public bucket so the web app can render it, writes the new status, marks the plan step
pending-human-input (BLOCKING tasks only), and publishes a worklog. So after start, never
re-upload the request artifact, never write the task status yourself, and never push a plan-step
update to announce the task — you would create a duplicate body or a conflicting step state.

Start is deliberately not idempotent. A second start throws *"Cannot call StartHitlTask on
already started task"* — read that as proof the task is live, and go poll.

## Polling: the answer, not the status word

**Poll with `get_hitl_task`. Never poll with `retrieve_hitl_output_as_string`** — that raises
whenever the human hasn't answered yet, which is the normal state of every poll before
submission, so it cannot tell waiting from broken.

End the loop when **the answer exists**: `humanArtifact.artifactId` is present, or the status is
`SUBMITTED` or `CLOSED`. Do not wait for the literal `SUBMITTED` — a `NON_BLOCKING` feedback task
goes straight to `CLOSED` on submit, and a loop watching for `SUBMITTED` hangs forever on a task
the user already answered. When you land on `CLOSED`, read the output and skip step 7; the
platform already closed it.

Branch on what you see:

| Status | Meaning | Do |
|---|---|---|
| `CREATED` | start never landed | call `start_hitl_task` |
| `AWAITING_HUMAN_INPUT` / `IN_PROGRESS` | healthy, waiting | keep polling (check `action` — see rejection) |
| `SUBMITTED` / answer artifact present | answered | read it |
| `CLOSED` | answered and auto-closed | read it, do not close |
| `CANCELLED` | someone killed it | stop polling |

While you wait: announce in chat what you need and why — nothing pushes a regular task to the
user, so an unannounced task sits in a list nobody is looking at. Then let `blocking_type` decide
your behavior: on `BLOCKING`, the next step depends on the answer, so wait; on `NON_BLOCKING`, the
job does not pause, so go do the work that does not depend on the answer and poll back later.

## Approval gates (mandatory before mutations)

Before anything that changes customer resources or spends money, run exactly this order:

1. Persist the approval summary (what will run, on what, expected effect) — see `artifact-io`.
2. Create the task with `blocking_type="BLOCKING"` and `severity="CRITICAL"` passed
   **explicitly**. The autoform/autotable helpers default to `NON_BLOCKING`/`STANDARD` while raw
   `create_hitl_task` defaults to `BLOCKING` — so never rely on the default. A gate created with
   the helper defaults does not pause the job and does not mark the plan step: it is a suggestion,
   not a gate.
3. Start it (the helpers already did).
4. Poll, 5. read the answer, 6. close with `closure_type="CLOSED"`.
7. **Only then** perform the mutation.

Your creation surface has no task-category parameter, so this is a regular task marked CRITICAL,
not a platform TOOL_APPROVAL task — the CRITICAL+BLOCKING framing is what makes it the decision
record. A chat "yes go ahead" is not an approval: it leaves no record the platform can enforce.

## Rejection means rework, not failure

`IN_PROGRESS` is ambiguous — a rejected task and a freshly started chained task both sit there.
Read the task's **`action`** field on every poll: `REJECT` is a rejection, `APPROVE` is a
submission. Treat `SUBMITTED` → `IN_PROGRESS` as "rework requested".

On rejection, reuse the SAME task: acknowledge it in chat, ask what needs to change, and resume
polling the same `hitl_task_id`. Do not create a replacement, do not call start again, and do not
try to read the artifact of a rejected task — get the reason from the user in chat.

## Which creation tool

| Situation | Tool |
|---|---|
| Structured input (several values, choices, files) | `create_autoform_hitl_task` |
| Tabular review/selection | `create_autotable_hitl_task` |
| Custom component you already have an artifact for | `create_hitl_task` |

Pass a plan step id so the task renders on the right step. For form and field design (which field
types capture input, validation), load `hitl-forms`.

Two rules that outlive the interaction: **always pass `closure_type` explicitly** (the default is
`CANCELLED`, which permanently records a completed interaction as discarded), and **close only
after you have the answer** — closing a task the human is mid-form on destroys their submit.

## Symptoms and causes

| Symptom | Cause | Fix |
|---|---|---|
| User says "I don't see any task" | `start_hitl_task` never called, or step id invalid | start it; verify the step id |
| "Cannot call StartHitlTask on already started task" | the task is already live | stop starting, start polling |
| Poll never terminates | waiting for literal `SUBMITTED` on a task that went to `CLOSED` | exit on the answer artifact or `CLOSED` too |
| `retrieve_hitl_output_as_string` keeps raising | used as the poll signal before submission | poll `get_hitl_task`; read only once the answer exists |
| Task recorded as cancelled though the user answered | `close_hitl_task` without `closure_type` | always pass `closure_type="CLOSED"` |
| Approval "granted" but nothing recorded | approval was chat-only | redo as a CRITICAL + BLOCKING task |
| Mutation ran but the job never paused for it | gate created with helper defaults (`NON_BLOCKING`) | pass `BLOCKING`/`CRITICAL` explicitly |
| Plan step stuck pending-human-input with no open task | a duplicate/abandoned task was never closed | see `references/recovery.md` |

## References

- `references/recovery.md` — when a call fails or you suspect a duplicate task: failed starts,
  retry rules, duplicate cleanup, closure corrections, and why the plan step is not a health signal.
- `references/task-shapes.md` — per-variant behavior: chaining, reading output by
  component type, and severity.
