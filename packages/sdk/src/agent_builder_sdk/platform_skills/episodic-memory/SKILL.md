---
name: episodic-memory
description: Use to remember findings, decisions, and outcomes across the job so nothing important is lost, and to recall what you learned earlier — especially after a resume. Covers the memory tool's store and retrieve operations for episodic memory.
---

# Episodic Memory

The `memory` tool is your durable notebook for the job: a running record of what you learned,
decided, and did, so a later turn (or a resume in a fresh container) can pick up with that
context instead of rediscovering it. It is job-scoped — you're always reading and writing this
job's episodes.

Two operations:

- `memory(operation="store", content="...")` — record one episode. `content` is a short
  plain-language note of a specific finding, decision, or outcome.
- `memory(operation="retrieve", limit=10)` — return recent episodes (most useful at the start
  of a turn when you need to reconstruct where things stand).

## What to store (and what not to)

Store the things that would be expensive to rediscover or costly to get wrong later:

- Key **findings** — "source bucket has 3 partitioned Parquet datasets under /raw; schema has a
  nullable `event_ts` timestamp."
- **Decisions** and their rationale — "user chose Iceberg over Delta because they're on Athena."
- **Outcomes** — "migration dry-run succeeded on the sample; full run pending approval."

Skip the ephemeral: routine tool mechanics, step-by-step narration, and anything already
captured as a worklog or artifact. Memory is for the durable "why" and "what we know," not a
transcript.

## When to use it

- Store an episode as you reach each finding/decision/outcome — while it's fresh, not in a
  batch at the end.
- Retrieve at the start of a turn when you're unsure what's already been established, and
  especially on resume (pair with `get_job` / `list_worklogs` — see job-plan) to rebuild your
  bearings before acting.

## Rules

- Keep each episode self-contained and specific — a note you'd understand cold, with no
  surrounding conversation.
- Never put credentials, secrets, or raw customer data in an episode.
- Memory is your working context, not a user deliverable — anything the user needs is a
  worklog or an artifact (see artifact-io), not a memory.
