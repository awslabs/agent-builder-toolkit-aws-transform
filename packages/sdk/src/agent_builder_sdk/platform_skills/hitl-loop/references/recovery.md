# HITL Recovery

Read this when a HITL call fails, a task seems missing, or you suspect you created a duplicate.
The theme: **recover by discovery, never by retrying a create.**

## A `start_hitl_task` that errored

Retry `start_hitl_task` with the SAME `hitl_task_id`. The status is written only after the
artifact copy succeeds, and the write requires the task to still be `CREATED`, so a failure
anywhere in that path leaves the task startable.

Check first with `get_hitl_task`:

- `CREATED` → start never took effect. Retry start.
- anything else → start already succeeded. Stop retrying and poll.

Never create a replacement task for a failed start. A failed start looks identical to a missing
task from the user's side (both invisible), and creating a "fresh one" leaves two live tasks on
the same step.

## Never blind-retry a create

Every create call mints a fresh idempotency token, so **a retry is a brand-new task, not a
replay**. After a timeout or an ambiguous error on any `create_*` call, do not call it again.

Recover by discovery instead:

1. `list_hitl_tasks(task_type="NORMAL")` and look for the orphaned unstarted task — match it by
   the `tag` you passed, or by its plan step id and title.
2. `start_hitl_task` on the one you find.

Because of this, **pass a unique `tag` on every create**. It is the only reliable way to find a
half-finished create afterward. (`list_hitl_tasks` also accepts a status/step/tag filter, but the
tool's filter field names have drifted from the service model — match on the returned tasks rather
than trusting a filter to do it.)

## You created a duplicate

Do not ignore the extra one. Pick the task you will poll — prefer whichever the user has already
touched (status `IN_PROGRESS`, or an answer artifact present) — and close the other with
`closure_type="CANCELLED"`.

An abandoned BLOCKING task keeps its plan step marked pending-human-input forever: nothing in the
platform retires that marker, and the task stays in the user's pending list indefinitely.

## Never close a task you still want answered

Not on a poll timeout, not while "cleaning up", not before a retry. The human's submit is only
accepted while the task is open; once you move it to a closed state, a submit already in flight
fails validation and **their work is discarded**. If a task is taking too long, prompt again in
chat and keep polling.

Close only after you have read the output, or when you have genuinely decided to abandon the ask.

## `closure_type` is a one-way decision

Decide before you call close. Closing again from a terminal state fails with *"Task is in a
different terminated status"*, and the only permitted correction is `CLOSED` → `CANCELLED`. There
is no path back from `CANCELLED`, and none out of `CLOSED_PENDING_NEXT_TASK`.

Repeating the *identical* close is safe (it returns the current status unchanged), so retrying a
close after a timeout is fine — changing your mind is not.

## Closing does not release the plan step

`close_hitl_task` touches only the task and its worklog. Start is what marked the plan step
pending-human-input, and close does not undo it. After closing a BLOCKING task, drive the plan
step to its next status yourself (see `job-plan`) — otherwise the plan shows a step waiting on a
human with no open task, and the job looks stuck to the user.

## The plan step is not a health signal

Never confirm your task is live by looking at the plan step. The step update on start is
fail-open: if it fails, the task is still correctly awaiting input while the step looks untouched.
It is also skipped entirely for `NON_BLOCKING` tasks and when no step id was stored.

Confirm liveness from `get_hitl_task` status only. An agent that checks the step instead
concludes the start failed and recreates a task the user can already see.
