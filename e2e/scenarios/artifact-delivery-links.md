# Scenario: an agent's reply links the customer file it delivered

Verifies artifact delivery links (PR #116) the way a partner developer would meet it: find it in
the toolkit docs, build an agent in Kiro that uploads a customer file with `visibility="EXTERNAL"`
and adds the SDK's `ArtifactDeliveryHookProvider`, deploy and register that agent, and use it in
an AWS Transform job. The model is told to write no links, so a link in the reply comes from the
SDK. The run does not cover streamed (`message/stream`) turns. Every prompt below is typed
verbatim by the simulated builder. Placeholders in `{braces}` are filled by the runner (see
`e2e/README.md`).

```json scenario
{
  "id": "artifact-delivery-links",
  "title": "An agent's reply links the customer file it delivered",
  "pr": 116,
  "agent": "artlink-",
  "chat_label": "Artifact Links",
  "workspace": "toolkit-pr-e2e",
  "job": "Artifact-Links",
  "chat": {
    "deliver": {
      "has": ["](aws-transform://~/artifacts/"],
      "lacks": ["artifacts/delivery-note.md"]
    },
    "no-file": { "lacks": ["aws-transform://"] }
  },
  "logs": {
    "has": ["Turn delivered 1 user-visible artifact(s)"],
    "lacks": ["Failed to record a delivered artifact", "Failed to append artifact deeplinks"]
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
do I add artifact links to my agent's replies for customer files". Then read, in /kiro/.venv, the
full dev guide section the dev guide results come from (dev_guide.md in the same agent_builder_mcp
package), and answer in at most six lines: name the hook class and where it is imported from, the
upload settings a file needs to get a link, the tool call that must follow the upload, and cite
the doc section you found.
```

Expected: the answer cites the dev guide section "Artifact Links in Replies" and names
`ArtifactDeliveryHookProvider` (from `agent_builder_sdk.orchestrator_strands.hooks`),
`CUSTOMER_OUTPUT` with `visibility="EXTERNAL"`, and `get_artifact_metadata` after the upload.
That section exists only at the PR commit, so this also checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its artifact delivery hook and the dev guide
section on artifact links in replies.

Goal: in an AWS Transform job chat, when I ask for the delivery note, the agent uploads it as a
customer file and its reply lets me open that file.

Fixed choices:
- An agent factory like the one in the dev guide's artifact links section: the SDK's async
  orchestrator factory with the mcp_client the server passes (the AWS Transform platform tools),
  plus ArtifactDeliveryHookProvider added to the orchestrator's hooks. Do not turn on streaming.
- One custom tool, write_delivery_file(file_name, content): it writes the text to
  /tmp/deliverables/<file_name> and returns the file path and the base64 of the file's SHA-256
  digest (the format create_artifact_upload_url takes). No other custom tools, no other MCP
  clients.
- The entrypoint calls the SDK's configure_logging(), so the SDK's own log lines reach
  CloudWatch, then runs AgentRuntimeServer with delayed_timeout=3600 and binary_location set to
  the agent-builder-agentic-mcp command the image installs.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt says: only when the user asks for the delivery note, call
  write_delivery_file with file name delivery-note.md and this content:
  "# Delivery note" and then the line "All three applications were assessed."; then
  create_artifact_upload_url with artifactType categoryType CUSTOMER_OUTPUT and fileType
  MARKDOWN, visibility EXTERNAL, label "Delivery note" and the returned digest; then
  upload_artifact with the returned URL, headers, artifact ID and file path; then
  complete_artifact_upload; then get_artifact_metadata for that artifact ID. Then reply with one
  sentence that says the delivery note is ready. Upload nothing for any other message, and
  answer it in one sentence. Call get_artifact_metadata only as part of that delivery sequence.
  Never write a link, a URL or an artifact ID in a reply.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint
does (no MCP client), check that an ArtifactDeliveryHookProvider is registered on it and that
write_delivery_file is in the model's tool list, call write_delivery_file with the note above and
check that its digest matches the file, and print what the SDK's Deeplinks.artifact returns for
display text "Delivery note" and artifact_id "a1b2c3d4". Show me the results. Do not build or
deploy yet.
```

Expected: the hook is registered; `write_delivery_file` is in the tool list; the digest is a
44-character base64 string that matches the file; `Deeplinks.artifact` returns
`[Delivery note](aws-transform://~/artifacts/a1b2c3d4)` (the ID, not a file name, is the last
segment); the entrypoint calls `configure_logging()` before it starts the server. Without the PR,
the hook import fails.

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
`STAGE=prod`. `STAGE=prod` also means the agent logs at INFO, so its own log holds the SDK's
delivery line.

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
job with the **{chat_label}** agent and rename it, then send the two messages below in order, each
one after the reply to the message before it.

```web deliver
Please send me the delivery note for this job.
```

Expected: the reply says the delivery note is ready and ends with a link labelled **Delivery
note**; its target is an `aws-transform://~/artifacts/` deeplink whose last segment is the
artifact ID, not the file name. The model was told to write no links, so the SDK added it. An
agent without the PR replies with the sentence only, and no link. Click the link: the delivery
note opens.

```web no-file
Thanks. In one sentence, what can you help me with in this job?
```

Expected: a one-sentence answer with no link: this turn delivered no file, and the SDK does not
carry the first turn's link over.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
the hook's line that the turn delivered one user-visible artifact, and no failure to record a
delivered artifact or to append its link.

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
