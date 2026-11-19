# Plan Recovery

Read this when a plan write fails, times out, conflicts, or you have lost your step ids.

## `put_job_plan` timed out or its outcome is unknown

**Do not resend it.** Every attempt mints fresh random step ids, so a retry of a call that
actually succeeded creates a complete duplicate set of steps — and nothing afterward tells you
which set is which.

Recover by reconciling:

1. `list_job_plan_steps`.
2. Match on `stepLabel` — that is why labels must be unique across the whole job.
3. Re-put only what is genuinely missing (as an `append`, not an override).

## "Job plan updates cannot be made while existing updates are in progress"

Two plan writes overlapped, and the later one was rejected.

Serialise your plan writes: one `put_job_plan` at a time, and never fire a second because the
first seemed slow. On this error, pause, `list_job_plan_steps`, and re-put only what's missing.

## ConflictException

Do not loop on it.

Back off, re-read state (`get_job` + `list_job_plan_steps`), decide whether your write is still
the right one, then retry at most once.

If the conflict surfaced as *"Attempting to update a plan step that is in a terminal state"*,
something else already closed that step. Accept its state instead of overwriting it.

## "Cannot perform this action as the job is in the process of being started or stopped"

You tried to write while the job was still `CREATED`/`STARTING` (or already `STOPPING`). The whole
call is rejected, step update included.

Recovery: `get_job`, wait until the job has left the startup states, then re-issue the same write.
This is also why your first `update_job_status` should follow a `get_job` — sending `PLANNING`
while the job is still `STARTING` gets *"Invalid job status transition"*.

Keep the rest of the status sequence correct yourself, following the ordering rules in `job-plan`.

## Re-deriving lost step ids

`list_job_plan_steps` is the recovery path any time you have lost your mappings. It returns the
current version's live, non-deleted steps in score order.

To check a cached id cheaply, compare its **first four characters** with the prefix of the ids in
a fresh listing:

- Same prefix → your id is still valid.
- Different prefix → an override re-versioned the whole plan. Every id you hold is dead. Rebuild
  your label→id map from the listing, and tell the user which attachments were orphaned rather
  than silently continuing.

## Duplicate steps you can't tell apart

If reconciliation leaves two steps for the same work, keep the one with attachments (worklogs or
a HITL task already reference it) and delete the other, leaves first. If both have attachments,
keep both and rename nothing — instead mark the redundant one `FAILED` with a worklog explaining
it was superseded, so the user's view stays honest.
