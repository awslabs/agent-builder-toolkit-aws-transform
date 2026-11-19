# Instructions for coding agents

## End-to-end check: add the scenario to the pull request

A pull request that adds or changes a feature in `packages/` carries its own end-to-end scenario.
A simulated developer (an AI agent) follows the scenario in a real AWS test account: it installs
the toolkit from the pull request's commit, builds and deploys an agent, and uses the feature in an
AWS Transform job. A change to docs, tests or CI only needs no scenario.

1. Open the pull request, then add `e2e/scenarios/<feature>.md` with `"pr"` set to its number.
   The run reads `e2e/scenarios/` from the pull request at the reviewed commit and uses only the
   scenario whose `pr` is that number. A scenario on `main` counts only after you merge `main`
   into the pull request.
2. Copy `e2e/scenarios/a2ui-surfaces.md` and follow "Write a scenario" in `e2e/README.md`. The
   feature check (`surface` or `chat`, and optionally `logs`) must fail when the feature is
   missing.
3. Keep the scenario at most 400 lines and 20,000 bytes, with no account IDs, no HTML comments and
   no characters that a reader does not see. `pr` is a JSON number, and no other scenario may have
   it. `chat_label`, `workspace` and `job` use only letters, digits, spaces and hyphens (at most
   40 characters). Do not change a `.gitattributes` file in the same pull request: merge such a
   change on its own first.
4. Run `python -m pytest tests/test_e2e_scenarios.py`. CI runs it too, but it does not check every
   rule in step 3: the run refuses such a scenario before it starts.

A maintainer reviews the scenario like code, then starts the run (see "Ask for a run" in
`e2e/README.md`). The result comes back on the pull request as a comment and a
`simulated-builder` commit status. A new push needs a new run.
