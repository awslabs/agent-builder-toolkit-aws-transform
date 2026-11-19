# Scenario: an agent keeps an oversized tool result out of its context

Verifies `ToolOutputOffloader` (PR #111) the way a partner developer would meet it: find it in the
toolkit docs, build an agent in Kiro whose tool returns a very large JSON result, add the
offloader, deploy and register that agent, and use it in an AWS Transform job. The run checks
that the result is replaced by a preview and a reference, that the reference names a generated
file and not the tool-use id, and that the stored JSON is split into one value per line. It does
not check a checkpoint restore, concurrent streaming or a sandboxed agent. Every prompt below is
typed verbatim by the simulated builder. Placeholders in `{braces}` are filled by the runner (see
`e2e/README.md`).

```json scenario
{
  "id": "tool-output-offloader",
  "title": "An agent keeps an oversized tool result out of its context",
  "pr": 111,
  "agent": "offload-",
  "chat_label": "Offload Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Offload-Demo",
  "chat": {
    "inventory": {
      "has": ["[Offloaded: 1 blocks, ~", "[Stored references:]", "327413 chars"],
      "lacks": ["tooluse_"]
    },
    "read-lines": {
      "has": ["[Lines 1-6 of 18004]"],
      "lacks": ["[Lines 1-1 of 1]"]
    }
  },
  "logs": {
    "lacks": ["the full result stays in context"]
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
can my agent keep a very large tool result out of the model context". Then read, in /kiro/.venv,
the SDK file the top result names, and answer in at most six lines: name the class, how an
orchestrator turns it on, the default size above which a result is moved out, the tool the model
uses to read the rest, and cite the doc entry you found.
```

Expected: the answer names `ToolOutputOffloader`
(`agent_builder_sdk/orchestrator_strands/tool_output_offloader.py`, or the developer guide
section "Offload Large Tool Results (Optional)"), says it goes in the `plugins` argument of the
orchestrator constructor, gives 12500 tokens as the default limit, and names
`retrieve_offloaded_content`. That class and section exist only at the PR commit, so this also
checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its ToolOutputOffloader module, and the toolkit's
developer guide section on offloading large tool results.

Goal: in an AWS Transform job chat, the agent reads a very large application inventory from a
tool, and I want to see what the model gets instead of the whole result, and that it can read
parts of the stored result later in the job.

Fixed choices:
- One Strands @tool, list_inventory, with no arguments. It returns a str, exactly
  json.dumps({"records": records}) with the default separators (one line, no indent), where
  records is, for i from 1 to 3000: {"id": f"app-{i:05d}", "team": f"team-{i % 7}",
  "version": f"{i % 5}.{i % 11}.0", "status": "failed" if i % 97 == 0 else "ok"}.
- An agent factory that takes (mcp_client, storage_dir), as the developer guide's first example does
  (no concurrent streaming), and returns AsyncBaseOrchestrator with custom_tools set to
  list_inventory, mcp_clients=[mcp_client] when one is passed (else None), and the SDK's
  ToolOutputOffloader on that storage_dir in plugins, with its default limits. No other tools or
  plugins.
- The entrypoint calls the SDK's configure_logging(), so the SDK's warnings reach CloudWatch, then
  runs AgentRuntimeServer with that factory and delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt says: when I ask for the inventory, call list_inventory once, then reply with
  only the first line and the last two lines of the tool result exactly as you received it, each
  cut to its first 120 characters, in one code block, with nothing added; when I ask to read lines
  of the stored inventory, call the tool that reads offloaded content once, with the reference
  from that earlier result and the line range I give, then reply with only what that tool
  returned, in one code block, with nothing added, removed or changed. Never call list_inventory
  again for that, and never write output a tool did not return.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint
does, with a temporary storage directory, and check that its tools hold list_inventory and the
offloader's retrieval tool. Call list_inventory directly and print the length of its result, its
number of lines and its first 40 characters. Show me the results. Do not build or deploy yet.
```

Expected: the tools hold `list_inventory` and `retrieve_offloaded_content`; the result is 225405
characters on 1 line and starts `{"records": [{"id": "app-00001"`; the offloader is in `plugins`
of the orchestrator constructor (the `create_*` factories take no plugins); the entrypoint calls
`configure_logging()` before it starts the server.

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
`STAGE=prod`. `STAGE=prod` also means the agent logs at INFO, so a failed offload would show
its warning in the log.

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
job with the **{chat_label}** agent and rename it, then send the two messages below in order,
the second one after the reply to the first.

```web inventory
Show me the application inventory.
```

Expected: the reply holds the offloader's notice in place of the JSON: a first line that counts
1 offloaded block and its tokens, and the stored-references list, whose reference is a generated
id followed by `_0` and `(text, 327413 chars)`, the size of the result stored one value per line.
An agent without the PR shows the start of the JSON itself; one built on the plain Strands
offloader names a reference that holds the tool-use id (`tooluse_..._0 (text, 225405 chars)`).

```web read-lines
Read lines 1 to 6 of the stored inventory.
```

Expected: the reply holds the retrieval tool's header for lines 1 to 6 of 18004 lines, and the
lines `{`, `"records": [`, `{`, `"id": "app-00001",`, `"team": "team-1",`, `"version": "1.1.0",`,
indented two spaces per level, each on its own numbered line. 18004 lines means the one-line
JSON was stored one value per line, which only the PR does; stored as returned, the file has 1 line.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
no warning that an offload failed and the full result stayed in context.

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
