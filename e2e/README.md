# End-to-end: a simulated builder verifies a pull request

Unit tests and the offline `evaluation/` suite check the code. They don't check what a partner
developer actually meets: install the toolkit, ask Kiro to build an agent with the new feature,
deploy it, register it, and see it work in an AWS Transform job. This directory holds the
scenarios that a simulated developer runs against a PR's head commit to check exactly that.

```
 maintainer ── reviews the PR at one commit, runs "Simulated builder" from main (PR number + SHA)
                  └─► status "simulated-builder: pending"  (no checkout, no secrets, no AWS access)
 test account ── reads GitHub's public run list; accepts only this workflow, on main,
                 started by a maintainer, whose SHA is still the PR head
              ── a simulated developer (an AI agent) follows e2e/scenarios/<feature>.md in Kiro:
                   install the toolkit from the commit's source archive → build an agent
                   → deploy it → register it in AWS Transform → use it in a job → clean up
              ── verdict from evidence ──► PR comment + "simulated-builder: success | failure"
```

GitHub cannot start anything in the test account and holds no AWS credentials. The verdict comes
from evidence, not from the AI developer's report: package provenance (PEP 610 `direct_url.json`
names the commit), account state (build, runtime, registry entry), the feature in the web app
(DOM and API responses), cleanup (agent deregistered) and zero deviations from the scenario.
PR code runs only in a disposable environment that each run creates and deletes. A run takes
about an hour; it is not part of `ci.yml`.

## Ask for a run

Maintainers: open **Actions → Simulated builder → Run workflow**, keep the branch `main`, and
enter the PR number and the head commit you reviewed. Or:

```
gh workflow run simulated-builder.yml --ref main -f pr=<number> -f sha=<head commit>
```

The run reads `e2e/scenarios/` from the PR at the commit you reviewed and follows the scenario whose
`pr` field is the PR number, so the PR must contain it: add the scenario in the PR, or merge `main`
into the PR if the scenario is already on `main`. A scenario tells an AI agent what to type in a
real AWS account: review all of it like code, in the source diff and not the rendered view, before
you start the run. A new push is not tested until a maintainer reviews it and starts a new run with
the new SHA. So that the diff shows the whole scenario, the run stops when the scenario has more
than 400 lines or 20,000 bytes, or when a `.gitattributes` file at the top, in `e2e/` or in
`e2e/scenarios/` is not the same as on `main`: merge such a change on its own first. Start no run
when **Files changed** says that a file or a part of the diff is not shown. The run starts at the
earliest 10 minutes after you ask for it, and later while other runs use all build slots.

## Write a scenario

Copy `scenarios/a2ui-surfaces.md`. A scenario is plain Markdown that a person can follow too:

- One ```` ```json scenario ```` block: `id`, `title`, `pr`, `agent` (a lowercase prefix of at
  most 11 characters ending in `-`; the runner appends the account ID), `chat_label`, `workspace`,
  `job`, and the feature check: `surface` or `chat` (or both), and optionally `logs`.
  - `surface`: an A2UI surface that the job chat must render (`component`, `text`, `suggestions`).
  - `chat`: `{"<web block name>": {"has": [...], "lacks": [...]}}`. The text that the agent adds
    to the job chat after that message must hold every `has` string and no `lacks` string.
  - `logs`: `{"has": [...], "lacks": [...]}`, the same check on the deployed agent's own log
    (CloudWatch), read after the last `web` block, one log event at a time.
  - In `chat` and `logs`, matching is exact and case-sensitive, after commas between digits are
    removed (write `165000`). No `has` string may be in a `kiro` or `web` block: a value from a
    prompt can pass without the feature (the job chat shows your own message).
- ```` ```kiro <name> ```` blocks: prompts typed into Kiro, in order. The first is `install`, the
  last ones `cleanup` (and `cleanup-force`).
- ```` ```web <name> ```` blocks: messages typed into the AWS Transform job chat.
- After each block, an **Expected** line: what the developer must see before going on.

Placeholders the runner fills: `{pr}`, `{commit}`, `{short}`, `{repo}` (the PR's head repository),
`{archive}`, `{pip}` (pip requirements for all five packages at the commit), `{pip_runtime}` (the
four the agent image needs), `{mcp_from}` (the MCP server at the commit, for `uvx --from`),
`{agent}`, `{chat_label}`, `{workspace}`, `{artifact_bucket}` (the test account's bucket for build
sources), `{build_role}` (the existing CodeBuild service role for agent images). Write prompts the
way a developer would; say what to build and what to check, not how the harness works. Never put
account IDs in a scenario. `tests/test_e2e_scenarios.py` checks the format in CI.

## Known workarounds in the scenarios

- Registration goes through `_register_with_atx` with a wrapper that sets
  `agentCard.capabilities.allowChatWhenJobTerminated`, because the toolkit's registry path doesn't
  send it and the registry now requires it. Once the toolkit sends it, register through the MCP
  tool and drop the wrapper.
