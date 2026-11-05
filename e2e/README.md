# End-to-end: a simulated builder verifies a pull request

Unit tests and the offline `evaluation/` suite check the code. They don't check what a partner
developer actually meets: install the toolkit, ask Kiro to build an agent with the new feature,
deploy it, register it, and see it work in an AWS Transform job. This directory holds the
scenarios that a simulated developer runs against a PR's head commit to check exactly that.

```
 PR ── maintainer adds label e2e:simulated-builder
  │        └─► .github/workflows/simulated-builder.yml: commit status "simulated-builder: pending"
  │            (no checkout, no secrets, no PR code)
  ▼
 maintainer's runner (AWS-side)
  ├─ uses a disposable AWS test account with Kiro in the browser
  ├─ a simulated developer (an AI agent) follows e2e/scenarios/<feature>.md:
  │     Kiro installs the toolkit from github.com/<head repo>/archive/<commit>.tar.gz
  │     → builds an agent with the feature → CodeBuild image → Bedrock AgentCore
  │     → registers it in AWS Transform → uses it in a job → deregisters it
  │   It only types the scenario's prompts and reviews each Kiro command under fixed rules.
  ├─ the verdict comes from evidence, not from the agent's report:
  │     package provenance (PEP 610 direct_url.json names the commit), account state
  │     (build, runtime, registry entry), the feature in the web app (DOM + API responses),
  │     cleanup (agent deregistered), zero deviations from the scenario
  └─► PR comment with the checks + commit status "simulated-builder: success | failure"
```

PR code runs only inside the disposable account (Kiro, CodeBuild, AgentCore). A run takes about
an hour; it is not part of `ci.yml`.

## Ask for a run

Maintainers: add the `e2e:simulated-builder` label. The PR needs a scenario that exercises its
change, either an existing one in `e2e/scenarios/` or a new one added by the PR. A new push
re-queues the new head commit.

## Write a scenario

Copy `scenarios/a2ui-surfaces.md`. A scenario is plain Markdown that a person can follow too:

- One ```` ```json scenario ```` block: `id`, `title`, `pr`, `agent` (a lowercase prefix ending
  in `-`; the runner appends the account ID), `chat_label`, `workspace`, `job`, and `surface`,
  what the feature check looks for in the job chat (`component`, `text`, `suggestions`).
- ```` ```kiro <name> ```` blocks: prompts typed into Kiro, in order. The first is `install`, the
  last ones `cleanup` (and `cleanup-force`).
- ```` ```web <name> ```` blocks: messages typed into the AWS Transform job chat.
- After each block, an **Expected** line: what the developer must see before going on.

Placeholders the runner fills: `{pr}`, `{commit}`, `{short}`, `{repo}` (the PR's head repository),
`{archive}`, `{pip}` (pip requirements for all five packages at the commit), `{pip_runtime}` (the
four the agent image needs), `{mcp_from}` (the MCP server at the commit, for `uvx --from`),
`{agent}`, `{chat_label}`, `{workspace}`. Write prompts the way a developer would; say what to
build and what to check, not how the harness works. Never put account IDs in a scenario.
`tests/test_e2e_scenarios.py` checks the format in CI.

## Known workarounds in the scenarios

- Registration goes through `_register_with_atx` with a wrapper that sets
  `agentCard.capabilities.allowChatWhenJobTerminated`, because the toolkit's registry path doesn't
  send it and the registry now requires it. Once the toolkit sends it, register through the MCP
  tool and drop the wrapper.
