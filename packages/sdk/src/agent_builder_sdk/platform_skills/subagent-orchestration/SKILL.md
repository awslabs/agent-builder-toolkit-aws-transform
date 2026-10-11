---
name: subagent-orchestration
description: Use when delegating work to another agent - discovering registered subagents, invoking one, exchanging messages with it, and tracking its instance status. Covers the discover -> invoke -> message -> poll loop and its failure modes.
---

# Sub-agent Orchestration

Delegation is a four-step loop: discover what exists, invoke an instance, converse with
it, and track it to completion. Each step has a distinct tool and failure mode.

## 1. Discover

`discover_subagents()` is meant to list agents registered with the platform, with their cards
(name, description, skills). It currently returns placeholder data rather than real registry
results, so don't rely on its output as a real catalog — invoke an agent id only when it came
from the user or a source you trust, not from a fabricated card.

## 2. Invoke

```
invoke_agent(agent_id=..., agent_input={"serializedPayload": "<your input as one string>"})
  -> agent_instance_id
```

- `agent_input` must be a dict with the single key `serializedPayload` whose value is your
  entire input as ONE string (serialize a JSON payload to a string first). Don't pass raw
  dicts as values, and don't double-encode an already-serialized string.
- Save the returned `agent_instance_id`; it is the handle for everything that follows.
- Check for an existing running instance first (`list_agent_instances`) — invoking twice
  creates two workers on the same job.

## 3. Converse

`send_message_to_subagent(subagent_instance_id=..., message=...)` sends one message and
returns the reply. Treat the exchange as a conversation with an async worker:

- A slow or empty reply does not mean failure — the subagent may still be working. Check
  instance status before concluding anything.
- Keep messages self-contained: the subagent does not share your conversation history,
  only what you send it (plus the shared job state: plan, artifacts, worklogs).
- Exchange large data through artifacts (send the artifact id), never inline in messages.

## 4. Track and finish

`get_agent_instance(agent_instance_id)` returns the instance status. Poll it to decide when the
delegated work is done. A freshly invoked instance is `INVOKING`/`INVOKED` before it reaches
`RUNNING` — that's startup, not a hang. `RUNNING` means working; `COMPLETED`/`FAILED`/`STOPPED`
are terminal; `UNRESPONSIVE` means the platform lost contact (treat as failed after it
persists). Only `RUNNING`, `COMPLETED`, `FAILED`, `STOPPED` are states a subagent sets on
itself (step 4 below).

- Poll status rather than trusting the last message; the final message and the terminal
  status can arrive in either order.
- `stop_agent(agent_instance_id)` when the work is no longer needed — do not abandon
  running instances.
- If you are yourself a subagent: report your own terminal state via
  `update_agent_instance(agent_instance_status="COMPLETED"|"FAILED", ...)` with your
  output; your caller polls exactly the same way.

## Division of labor

You (the orchestrator) own the platform surface: the job plan, HITL tasks with the user,
approvals, and final deliverables. Subagents do the work you delegate. Do not delegate
the approval gate or plan ownership — human contact points stay with you unless the
subagent's card explicitly covers them.

## Symptoms and causes

| Symptom | Cause | Fix |
|---|---|---|
| Subagent errors on its input | payload double-serialized or a raw dict | serialize once; values are plain strings |
| "Failed" conclusion from a message timeout | reply slow while work continues | poll `get_agent_instance` before declaring failure |
| Two subagents doing the same work | invoked without checking existing instances | `list_agent_instances` first |
| Delegated work invisible to the user | subagent output never surfaced | attach its artifacts/worklogs to your plan steps |
