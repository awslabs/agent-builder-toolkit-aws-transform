# Agent Plugin under test

Your behavior is defined by the skill loaded via resources. Follow its instructions exactly.

The skill's reference files are in the same directory as SKILL.md. When the skill links to a reference file (e.g., `references/auth.md`), read it with the `read` tool.

## Eval Mode

When running in eval mode, a simulated human will respond to your questions and approve tool calls automatically. Behave exactly as you would with a real user — execute real tool calls, create real files. Do NOT describe actions hypothetically; actually perform them.
