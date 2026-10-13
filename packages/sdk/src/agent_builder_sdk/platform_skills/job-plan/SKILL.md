---
name: job-plan
description: Use when creating or changing the job plan, advancing step or job status, recording worklogs, or reorienting on an existing job. Covers put_job_plan, the plan step id every other object attaches to, update_job_plan_step, update_job_status, worklogs, and reading the job back. Load this FIRST if no plan exists yet.
---

# Job Plan and Lifecycle

The job plan is the root of a job: every HITL task, connector request, worklog, and
plan-attached artifact hangs off a **plan step id**. The plan is also what the user sees — it
renders as the job's step view, so a plan you keep current is the product's progress display,
and a plan you create once and never touch is a static list that makes a working job look dead.

## The three names of a step (don't mix them up)

| Name | Who sets it | Where it appears |
|---|---|---|
| `stepLabel` (e.g. `"gather-reqs"`) | you, in the `put_job_plan` request | your request + the returned `mappings` |
| `stepName` (e.g. `"Gather requirements"`) | you | the card title the user reads — never an id |
| step id (e.g. `0001-3f2a8c1e-…`) | the platform | everywhere else: `plan_step_id`/`step_id` args, worklogs, HITL tasks |

A step id is **not** a bare UUID: it is `<4-digit plan version>-<uuid>`. That prefix matters —
see "Changing the plan".

`put_job_plan` returns `mappings` from each `stepLabel` to its step id. Save them, and choose
labels unique across the whole job: the label is your only stable handle for re-deriving ids
later, and the platform only rejects duplicates within a single request.

## Creating the plan

```
put_job_plan(
    plan={"nodes": [
        {"stepLabel": "gather-reqs", "stepName": "Gather requirements", "description": "..."},
        {"stepLabel": "inspect-data", "stepName": "Inspect source data", "description": "..."},
    ]},
    mode={"override": {}},
)
# returns {"status": ..., "mappings": {"gather-reqs": "0001-<uuid>", ...}}
```

- Use `mode={"override": {}}` for the **first** plan of a run — and only then. Append before any
  override fails with *"Cannot append steps to a plan that does not exist yet."*
- Every node needs `stepLabel`, `stepName`, and `description`. Give each a real `stepName`: the
  user's step card falls back to the literal **"Untitled"** without one, and the `description` is
  the only body text on that card.
- Limits, enforced: `stepLabel`/`stepName` max 100 chars, `description` **max 350**, at most **80
  nodes per call** (sub-steps count).
- Write 2–6 top-level steps in the user's language. A one-step plan renders as a lone stub card.
- Verify success from the returned `mappings`, not the status — an empty `nodes` list is accepted
  as a no-op with zero mappings.

## Changing the plan mid-job

**Never call `override` twice.** It bumps the plan version and re-mints every step id, and the
service treats any id without the current version prefix as nonexistent. A second override
silently orphans every worklog, HITL task, and artifact you attached, and turns every id you
cached into a 404 — the user sees a plan that lost its history.

To revise scope, in order:

1. `list_job_plan_steps` — refresh the live ids.
2. New work → `put_job_plan` with `mode={"append": {"parentStepId": ..., "afterStepId": ...}}`.
   `parentStepId` is required: the literal `"root"` for a top-level step, or an existing step id
   to nest under. `afterStepId` is optional — omit it to land at the end of that level.
3. Save the new `mappings`.
4. Dropped work → `delete_job_plan_step`, **leaves first** (a step with children is rejected).
5. Reworded step → `update_job_plan_step` with a new `description`.

Every existing id survives all of this, because append reuses the current plan version. There is
**no reorder and no rename**: `update_job_plan_step` changes only status, times, and description.

For placement details and nesting rules, see `references/plan-shape.md`.

## The work rhythm: step status + worklog, together

Each step gets exactly one forward path, and each transition is paired with a worklog so the
user sees progress:

```
begin a step   -> update_job_plan_step(stepId, status="IN_PROGRESS", startTime=<now>)
                  + create_worklog(plan_step_id=stepId, description="what you're starting")
finish a step  -> create_worklog(plan_step_id=stepId, description="what you found/did")
                  + update_job_plan_step(stepId, status="SUCCEEDED"|"FAILED", endTime=<now>)
```

- `NOT_STARTED` is the platform's initial value — don't set it. `SUCCEEDED` and `FAILED` are
  terminal: stop writing to that step afterward.
- Never walk a step backwards.
- **Never set `STOPPED` yourself.** Use `FAILED` for abandoned work.
- The worklog is what the user actually reads. Write a full plain-language sentence — it is the
  entire visible payload of the row, and a step with no worklogs shows no progress at all.

## Blocking on a human

To pause the job for a human **without** a HITL task (for example, a plain-chat question), set
the owning step to `PENDING_HUMAN_INPUT` and stop. The platform detects that status and, in the
same write, flips the job to `AWAITING_HUMAN_INPUT` — so do **not** also call `update_job_status`.
For a **BLOCKING HITL task**, don't set the step yourself on the way in — `start_hitl_task`
already moves it to `PENDING_HUMAN_INPUT` (see `hitl-loop`).

Either way, **coming back off `PENDING_HUMAN_INPUT` is your job**, in this order:
`update_job_plan_step` off `PENDING_HUMAN_INPUT`, then `update_job_status` back to the phase you
were in. The platform sets `AWAITING_HUMAN_INPUT` on the way in but never unsets it, so the job
sits there until you move it — this holds for HITL tasks too; submitting the answer does not move
the step or job back.

## Job status

`update_job_status(status=..., status_info=...)`. Drive it `PLANNING` (drafting) → `PLANNED`
(only after the user approves) → `EXECUTING` (working) → `COMPLETED`, or `FAILED` with
`status_info`. If the runtime already moved the job to `EXECUTING` before your first turn, stay
there and get the plan approved through a HITL approval task instead of `PLANNED`.

`CREATED`, `STARTING`, and `ASSESSING` describe the job *before* you are running. The platform
owns them and you never set one: the product reads them as "the agent hasn't started" and takes
the chat input away from the user. Gather requirements while the status is `PLANNING`.
`AWAITING_HUMAN_INPUT`, `STOPPING`, and `STOPPED` are also the platform's.

Two ordering rules: never walk the status backwards (revise the plan while staying in
`EXECUTING`), and make `COMPLETED`/`FAILED` your **last** platform call — once terminal, every
plan write is rejected. Close open steps and post final worklogs first.

## Reorienting on an existing job

On resume, read where things stand before acting: `get_job` (objective, current status — and
**stop all work if `softDeleted` is true**), `list_job_plan_steps` (the plan and live ids),
`list_worklogs` (what's already done). Continue from there rather than replanning.

If a cached step id's 4-digit prefix differs from the ids in the fresh listing, an override
happened: rebuild your label→id map from the listing and tell the user what was orphaned.

## Symptoms and causes

| Symptom | Cause | Fix |
|---|---|---|
| HITL/connector task never appears for the user | `step_id` missing or not a platform id | `list_job_plan_steps`, retry with the real id |
| `put_job_plan` rejected / malformed | used `steps`/`stepId`/`title` or `mode={"type":...}` | use `nodes` + `stepLabel`/`stepName` + `mode={"override":{}}` |
| "Cannot append steps to a plan that does not exist yet" | append was the first plan call this run | put the full plan with `mode={"override":{}}` first |
| 404 on `update_job_plan_step` | a label/display name, or a stale id from before an override | use the id from `mappings`/`list_job_plan_steps` |
| Plan widget shows every step `NOT_STARTED` while you work | never called `update_job_plan_step` | advance each step as you work it |
| Step card titled "Untitled" | `stepName` missing | always set `stepName` |
| Worklog accepted but invisible on the step | wrong or missing `plan_step_id` | repost with the platform step id |
| Job stuck `AWAITING_HUMAN_INPUT` after the human answered | only the platform sets it, never clears it | move the step, then `update_job_status` back |
| User can't type in chat / "agent is initializing" | you set `ASSESSING` (or `STARTING`) | never set those; use `PLANNING` |
| "updates cannot be made while existing updates are in progress" | two concurrent `put_job_plan` calls | serialise plan writes; `list_job_plan_steps` then re-put only what's missing |
| "Attempting to update a job that is in a terminal state" | job already `COMPLETED`/`FAILED` | terminal status must be the last write of the run |

## References

- `references/plan-shape.md` — step placement, nesting, and deletion order.
- `references/plan-recovery.md` — timeouts, conflicts, duplicate steps, and re-deriving lost ids.
