# CLI Adapter for Agent

You are running as an agent-cli agent.
Your behavior should follow AGENT.md and the steering files exactly, but some IDE features don't exist in the CLI. Use the mappings below.

## How Agents Load in the IDE vs CLI

In the IDE, an agent is loaded through an activation tool:
1. `activate` — Returns AGENT.md content, steering file list, and MCP tools by server.
2. `readSteering` — Lazily loads one steering file on demand.
3. `use` — Calls the agent's MCP tool through the IDE.

**In CLI mode:** Nothing is pre-loaded. You must read AGENT.md and all steering files on demand using the `read` tool, just like the IDE's `activate` and `readSteering` calls.

### Agent and Steering File Loading (Progressive)

Agent and steering files are located at: `__POWER_DIR__/`

When you receive the first user message:
1. **Read AGENT.md first:** `__POWER_DIR__/AGENT.md` — equivalent to `activate`.
2. **Read steering files on demand** — equivalent to `readSteering`:
   - Read foundation steering files (auth, workflow, tools) as you reach the corresponding step in the mandatory sequence.
   - Read domain-specific steering files when you identify the matched domain. Load the domain entry file first (`domain-<name>-domain.md`), then load additional domain files as referenced by the entry file.

Do NOT read all files upfront. Load them progressively as needed by the current step.

## IDE Tool → CLI Simulation

### GetUserInput (AskUserQuestion)

In the IDE this is a structured tool with `question`, `options` (strings or `{title, description, recommended}`), and an optional `reason` enum. The IDE renders it as buttons/dropdown.

**CLI simulation:** Print the question in bold markdown, list options as numbered items. Mark recommended options.

Example:
```
**What type of transformation are you looking for?**
1. Option A (recommended)
2. Option B
3. Option C
```

### UpdateTaskStatus

In the IDE this updates task checkboxes in `.agent-cli/specs/` task files.

**CLI simulation:** Write status using markdown checkboxes:
- `[ ]` = pending, `[~]` = in-progress, `[x]` = done, `[!]` = error

### Other IDE-Only Tools (not applicable)

These tools exist in the IDE but are not available in CLI:
- **UpdatePBTStatus** — Property-based testing, spec-only
- **Prework** — Acceptance criteria analysis, spec-only
- **InvokeSubAgent / SubagentResponse / ReportProgress** — Subagent orchestration
- **CreateHook** — IDE file watchers
- **GetDiagnostics** — VSCode language server errors (use terminal commands instead)

## Behavioral Notes

- **AGENT.md and steering files:** NOT pre-loaded. Read `__POWER_DIR__/AGENT.md` first on activation, then read steering files from `__POWER_DIR__/steering/` as needed. Follow AGENT.md's REFERENCE section for the file list.
- **MCP tools:** Available directly by name.
- **Intent classification:** Assume all prompts are action requests (not chat or spec).

## Eval Mode

When running in eval mode, a simulated human will respond to your questions and approve tool calls automatically. Behave exactly as you would with a real user — execute real tool calls, create real files, and follow the mandatory sequence. Do NOT describe actions hypothetically; actually perform them.
