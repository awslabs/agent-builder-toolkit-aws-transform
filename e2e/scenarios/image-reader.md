# Scenario: an agent reads image files and its tool results keep images within the model's limits

Verifies the `image_reader` tool and `ImageBlockGuardHook` (PR #114) the way a partner developer
would meet them: find them in the toolkit docs, build an agent in Kiro that gets `image_reader`
through `custom_tools` and the hook on its orchestrator, deploy and register that agent, and use
it in an AWS Transform job. The agent has two small tools of its own: one draws a card with Pillow
and saves it as a file, the other returns a banner wider than the 8000 px that Converse accepts as
a raw image block. The run does not check the byte, pixel, time or file-type limits of the same
pull request, so a pass covers one downscaled read and one downscaled tool result only. Every
prompt below is typed verbatim by the simulated builder. Placeholders in `{braces}` are filled by
the runner (see `e2e/README.md`).

```json scenario
{
  "id": "image-reader",
  "title": "An agent reads image files and its tool results keep images within the model's limits",
  "pr": 114,
  "agent": "imgread-",
  "chat_label": "Image Reader Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Image-Reader-Demo",
  "chat": {
    "read-card": { "has": ["77057"] },
    "wide-banner": { "has": ["86299"], "lacks": ["not shown"] }
  },
  "logs": {
    "has": ["Normalized an image block from 'render_banner': png", "bytes -> jpeg"],
    "lacks": ["Dropping an image block"]
  }
}
```

## 1. Install the toolkit from the pull request

Open Kiro, select Claude Opus 5.5, install the AWS Transform Agent Toolkit power, and click
**Try power**. After its first approval (or about a minute), send:

```kiro install
Continue the onboarding. I'm testing a pre-release of this toolkit: pull request #{pr}, commit
{commit}. We'll build the agent image with AWS CodeBuild, so a local container runtime
(finch/docker) isn't needed.
- Install the toolkit packages from that commit, not from PyPI, into /kiro/.venv (run from
  /kiro; create nothing else). Use this command as is, then add pytest==9.2.0:
  /kiro/.venv/bin/pip install {pip}
  Show me the output of: /kiro/.venv/bin/pip list | grep agent-builder
- Register the botocore service models from the SDK you installed.
- The deployment roles are pre-provisioned in this account: AgentCoreExecutionRole and
  AWSTransformAgentInvokeRole. Verify they exist rather than creating them.
- Set up the workspace hook so it checks prerequisites before a build, deploy or register, and
  never blocks read-only toolkit calls.
```

Expected: five `agent-builder-*` packages listed; both roles found (not created); the hook
added. `pkg-proof` must say `ok: true`. The power's MCP server keeps running the released
toolkit: Kiro's permission policy (rightly) doesn't let an agent rewrite `~/.kiro/settings`, so
step 2 runs the commit's own search code from the venv instead.

## 2. Find the feature in the docs

```kiro discover
The power's MCP server runs the released toolkit, so search the docs of the commit under test
directly: with /kiro/.venv/bin/python, call the toolkit's own documentation search (the function
behind its keyword_search MCP tool, in the agent_builder_mcp package installed there) for "how
can my agent look at an image file such as a screenshot or a chart". Then read, in /kiro/.venv,
the SDK files the top results name and the SDK's README, and answer in at most six lines: name
the tool and the hook, how an agent gets each, what the hook does to an oversized image, and cite
the doc entries you found.
```

Expected: the answer cites the SDK doc entries for `image_reader`
(`agent_builder_sdk/orchestrator_strands/tools/image_reader.py`) and `ImageBlockGuardHook`
(`agent_builder_sdk/orchestrator_strands/hooks/image_block_guard.py`), says the tool goes in
`custom_tools` and the hook in the orchestrator's hooks, and says an image over 3.75 MB or 1568 px
per side is downscaled and re-encoded. Those entries exist only at the PR commit, so this also
checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its image_reader tool, its ImageBlockGuardHook and
the README section on reading image files.

Goal: in an AWS Transform job chat, the agent looks at images, both image files on disk and images
that a tool returns, and tells me what it sees, so I can check that it really reads them.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory, with custom_tools holding the SDK's
  image_reader and two tools of the agent's own, below. Add no other tools and no MCP clients.
  Add the SDK's ImageBlockGuardHook to the orchestrator's hooks, as the SDK README shows.
- Tool draw_card (no input): with Pillow, draw a white 3000x1000 RGB image with str(251 * 307) in
  black, centred, in Pillow's default font at size 700; save it as PNG to /tmp/pr114/card.png
  (create the folder) and return only the text "Saved /tmp/pr114/card.png". The returned text must
  not hold the number. The tool's name, docstring and description must not hold the number or the
  expression that makes it; describe the tool only as drawing a card.
- Tool render_banner (no input): with Pillow, draw a white 8200x2000 RGB image with str(409 * 211)
  in black, centred, in Pillow's default font at size 1500, and return it as a raw PNG image block
  of the tool result (format "png", the PNG bytes as the source bytes), with no text block and no
  file. The tool's name, docstring and description must not hold the number or the expression that
  makes it; describe the tool only as drawing a banner.
- The entrypoint calls the SDK's configure_logging(), so the hook's own log lines reach
  CloudWatch, then runs AgentRuntimeServer with delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt says: when the user asks for the card, call draw_card, then call image_reader
  with the path it returned, and reply with the number the image shows; when the user asks for
  the banner, call render_banner and reply with the number the image shows; reply with only the
  digits you read in the image, and if you cannot see an image, say so instead of guessing.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint does,
check that the model's tool list holds image_reader, draw_card and render_banner, print each
tool's description, and check that the orchestrator's hooks hold ImageBlockGuardHook. Call
draw_card, then image_reader with its path, and print the result's status, image format and pixel
size (decode the returned bytes with Pillow). Call render_banner and print its block's format and
pixel size. Show me the results. Do not build or deploy yet.
```

Expected: the tool list holds `image_reader`, `draw_card` and `render_banner`; neither the
`draw_card` nor the `render_banner` description holds the number its tool draws or the product that
makes it; the hooks hold `ImageBlockGuardHook`; `image_reader` returns `success` with a `jpeg`
1568 px wide, not the 3000x1000 PNG on disk; `render_banner` returns a `png` of 8200x2000; the
entrypoint calls `configure_logging()` before it starts the server.

## 4. Build the image and deploy it

```kiro deploy
Build and deploy my agent to Amazon Bedrock AgentCore in us-east-1. The agent name is {agent}
followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity), and the agent
folder is the /kiro folder of the same name.
There is no local container runtime, so build with your own CodeBuild project (not
atx-agent-builder):
- Zip the agent folder, excluding .venv, __pycache__ and .git, and upload it to
  s3://{artifact_bucket}/codebuild-source/
  <the agent name>/source.zip
- Create CodeBuild project <the agent name>-build with that S3 object as its
  source, the existing {build_role} as service role, environment type ARM_CONTAINER,
  image aws/codebuild/amazonlinux2-aarch64-standard:3.0, compute BUILD_GENERAL1_SMALL, and
  privileged mode on. Do not create or change any IAM role or policy.
- The buildspec logs in to ECR, creates the repository
  aws-transform-agents/<the agent name> if it is missing, builds the Dockerfile
  for linux/arm64, and pushes the :latest tag.
- Start the build and wait for SUCCEEDED.
Then deploy the pushed image with the toolkit's deploy_agent_to_agentcore, using the existing
AgentCoreExecutionRole. Wait until the runtime is READY and report the runtime ID and the exact
runtime ARN. Do not register the agent yet.
```

```kiro deploy-check
Show the runtime's network mode and environment variables.
```

Expected: build SUCCEEDED, runtime READY, network mode `PUBLIC`, `REGION=us-east-1`,
`STAGE=prod`. `STAGE=prod` also means the agent logs at INFO, so its own log holds the hook's
lines.

## 5. Register the agent

```kiro register
Register and publish my agent in AWS Transform as a job orchestrator. The agent name is
{agent}ACCOUNT_ID and the owner contact is toolkit-e2e-ACCOUNT_ID@example.com, where ACCOUNT_ID
is my 12-digit AWS account ID (get it with aws sts get-caller-identity). Use version 1.0.0, chat
UI label "{chat_label}", the runtime ARN from the deploy step, and the existing
AWSTransformAgentInvokeRole.

Don't use the toolkit's MCP registry tools for this: the toolkit doesn't send the now-required
agentCard.capabilities.allowChatWhenJobTerminated, and its publish_agent_version tool drops empty
{} and [] fields. Instead, run the toolkit's own _register_with_atx in-process, with
/kiro/.venv/bin/python (it has the toolkit from the commit under test):
- Turn on INFO logging so the helper's step messages print, then import
  agent_builder_mcp.tools.deployment._pipeline. Replace _pipeline.registry_client with a
  wrapper that returns the real client, but with publish_agent_version wrapped so it first sets
  configuration["agentCard"]["capabilities"]["allowChatWhenJobTerminated"] = False and then calls
  the original.
- Call _pipeline._register_with_atx with agent_name, agent_version="1.0.0", runtime_arn,
  access_role_arn (the AWSTransformAgentInvokeRole ARN in this account), registry_endpoint=None,
  owner_contact_info (the owner contact above), job_orchestrator=True and
  chat_ui_label="{chat_label}". Print the result. If it isn't success: true, stop there and show
  me the error.

Then, read-only, in the same script: with registry_client from
agent_builder_mcp.tools.registry._client, poll get_agent_version for up to 2 minutes until
version 1.0.0 is ACTIVE, and show its jobOrchestrator and jobOrchestratorMetadata.chatUILabel.
Do not deregister or delete anything.
```

Expected: `success: true`, version 1.0.0 `ACTIVE`, jobOrchestrator `true`, chat UI label as above.

## 6. Use it in AWS Transform

Sign in to the console, enable and open the AWS Transform web app, create the workspace, create a
job with the **{chat_label}** agent and rename it, then send the two messages below in order, the
second one after the reply to the first.

```web read-card
Show me the card.
```

Expected: the reply is the number drawn on the card. Only the pixels of the file hold it: the
system prompt and the tool descriptions do not, and draw_card returns only the path. So the agent
read the file with `image_reader`. An agent without the pull request has no `image_reader` (the
SDK has no such module, and `strands-agents-tools` 0.9 removed its own), so its build or its first
turn fails.

```web wide-banner
Show me the banner.
```

Expected: the reply is the number drawn on the banner. The tool returned an 8200 px wide PNG, over
the 8000 px that Converse accepts; the hook downscaled it to a JPEG before the model call. Without
the hook, Converse rejects the request and every later turn of the job, so no number comes back.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
the hook's line that it normalized the banner from a png to a jpeg, and no dropped image block.

## 7. Clean up

Stop the job, delete the workspace, then:

```kiro cleanup
My agent is {agent} followed by my 12-digit AWS account ID (get it with aws sts
get-caller-identity). Deregister it from the AWS Transform Agent Registry with deregister_agent,
without force. If the call is refused because of active instances in running jobs, stop and tell
me. Then poll GetAgent every few minutes until it returns ResourceNotFoundException.
```

```kiro cleanup-force
Retry the deregister with force=true. I checked that {workspace} is deleted and none of my jobs is
running, so go ahead without asking again. Then poll GetAgent every few minutes until it returns
ResourceNotFoundException.
```

Expected: `verify` says the agent is deregistered. The test account is reset after
the run, so the runtime, image and build project are not deleted here.
