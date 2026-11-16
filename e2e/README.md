# End-to-end: a simulated builder verifies a pull request

Unit tests and the offline `evaluation/` suite check the code. They don't check what a partner
developer actually meets: install the toolkit, ask Kiro to build an agent with the new feature,
deploy it, register it, and see it work in an AWS Transform job. This directory holds the
scenarios that a simulated developer runs against a PR's head commit to check exactly that.

```
 maintainer ── reviews the PR at one commit, runs "Simulated builder" from main (PR number + SHA,
                 scenario from main, from the PR or from another PR's commit)
                  └─► status "simulated-builder: pending"  (no checkout, no secrets, no AWS access)
 test account ── reads GitHub's public run list; accepts only this workflow, on main,
                 started by a maintainer, whose SHA is still the PR head
              ── a simulated developer (an AI agent) follows e2e/scenarios/<feature>.md in Kiro
                 (from main, or from the commit that the maintainer chose):
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

The run follows the scenario whose `pr` field is the PR number. The `scenario` input says where
the test account reads `e2e/scenarios/` from:

- `main` (the default): the scenarios on `main`.
- `pull-request`: the PR at the commit you reviewed, when the PR adds or changes its own scenario.
- a commit (40 hex characters) of another PR that holds the scenario. Its `pr` field must name the
  PR under test, not the PR that holds it. For example, PR #104 holds the scenario for PR #103:

```
gh workflow run simulated-builder.yml --ref main -f pr=103 -f sha=<reviewed head commit of #103> -f scenario=<reviewed commit of #104>
```

A scenario tells an AI agent what to type in a real AWS account. With `pull-request` or a commit,
review the scenario file at that commit like code, in the source diff and not the rendered view,
before you start the run. A new push is not tested until a maintainer reviews it and starts a new
run with the new SHA.

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
