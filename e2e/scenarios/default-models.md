# Scenario: an agent on the SDK's default Claude model holds a multi-turn chat with a tool call

Verifies the default model upgrade (PR #96) the way a partner developer would meet it: find the
default model in the toolkit docs, build an agent in Kiro on the SDK's default model, deploy and
register that agent, and chat with it in an AWS Transform job. Every prompt below is typed
verbatim by the simulated builder. Placeholders in `{braces}` are filled by the runner (see
`e2e/README.md`).

```json scenario
{
  "id": "default-models",
  "title": "An agent on the SDK's default Claude model holds a multi-turn chat with a tool call",
  "pr": 96,
  "agent": "model-",
  "chat_label": "Model Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Model-Demo",
  "chat": {
    "ask-cost": {"has": ["320000"]},
    "ask-next": {"has": ["360000"]},
    "ask-sum": {"has": ["680000"]}
  },
  "logs": {
    "has": ["Orchestrator initialized: model=us.anthropic.claude-sonnet-5-5",
            "No BedrockSharedCapacityRole available"],
    "lacks": ["Error invoking with source", "on-demand throughput",
              "bound to a different conversation"]
  }
}
```

The agent types no model ID. It reads the SDK's default (`anthropic.claude-sonnet-5-5` at this
commit) and adds the `us.` inference profile prefix, because Bedrock does not serve the bare ID
on demand (the developer guide says the same). No prompt holds the numbers in `chat`: only the
agent's tool can give the first two, and the third needs both earlier answers. `logs` holds two
SDK lines (the model ID that the agent passed, and the line the SDK writes only when it builds
the Bedrock model from that ID), the SDK's line for a failed model call, and the Bedrock errors
that this change is about. The run covers Sonnet 5.5 only: the Opus 5.5 default is in the
evaluation tools, which a run does not install.

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

## 2. Find the default model in the docs

```kiro discover
The power's MCP server runs the released toolkit, so search the docs of the commit under test
directly: with /kiro/.venv/bin/python, call the toolkit's own documentation search (the function
behind its keyword_search MCP tool, in the agent_builder_mcp package installed there) for "which
Bedrock model does my agent use by default and what IAM policy does it need". From the results,
answer in at most four lines: name the default Bedrock model and cite the doc section you found.
```

Expected: the answer cites the developer guide passage "Default Bedrock Model" and names
`us.anthropic.claude-sonnet-5-5`, and no Claude 4 model. The guide names Sonnet 5.5 only at the
PR commit, so this also checks the PR's docs and search index. The SDK's factories default to
the same model without the `us.` prefix; step 3 reads that default and adds the prefix.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv.

Goal: in an AWS Transform job chat, the agent answers questions about the migration cost of a
fixed application inventory over several turns, on the SDK's default model.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory. The agent runs on the SDK's default
  model through its US inference profile: the agent's code reads the default of the factory's
  model_id parameter with inspect and passes model_id="us." followed by that default. Pass no
  model, create no BedrockModel, and type no model ID anywhere in the agent.
- One custom tool, migration_cost(application). It returns the cost in US dollars as an integer:
  the application's lines of code times the rate of its language. The rates are in the tool's
  body only, not in its docstring: Java 3, .NET 4, Node.js 2 dollars per line. Add no other tools
  and no MCP clients.
- The entrypoint calls the SDK's configure_logging() first, then runs AgentRuntimeServer with
  delayed_timeout=3600.
- The system prompt holds the inventory: payments-api (Java, 120000 lines of code), ledger-svc
  (.NET, 80000), portal-web (Node.js, 45000). It does not hold the rates. It says: call
  migration_cost for the cost of an application and never work out that cost yourself.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint
does and show me the default of the factory's model_id parameter, the model ID that the agent's
model object sends to Bedrock (from the model's own config, not the agent's model_id attribute;
it must be "us." followed by the default), the model's tool list (it must hold migration_cost)
and the result of migration_cost for each application. Do not build or deploy yet.
```

Expected: the local check shows the default `anthropic.claude-sonnet-5-5`, the model ID
`us.anthropic.claude-sonnet-5-5` from the model object, `migration_cost` in the tool list, and the
costs 360000, 320000 and 90000. The agent's source types no model ID and passes no `model`, the
rates are only in the tool's body, and the entrypoint calls `configure_logging()` before it starts
the server.

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
`STAGE=prod`.

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
job with the **{chat_label}** agent and rename it. Then send the three messages in order, each
one after the answer to the one before. A first reply that says the agent is working on your
request is not the answer: wait for the next one. If none comes within five minutes, the agent
failed on that message: after that first reply the SDK does not send an error to the chat, and
the `logs` check shows the failed call.

```web ask-cost
What does it cost to migrate ledger-svc? Answer with the number only, in digits.
```

Expected (`chat` check): the reply holds 320000. Only the tool has the rates, so the model
called it.

```web ask-next
And for payments-api? Answer with the number only, in digits.
```

Expected (`chat` check): the reply holds 360000: a second tool call, with the first turn in the
stored history.

```web ask-sum
Add the two costs. Answer with the number only, in digits.
```

Expected (`chat` check): the reply holds 680000. The message names no application, so the model
had both earlier turns from the stored history. Then the `logs` check: the agent's log has the SDK
lines `Orchestrator initialized: model=us.anthropic.claude-sonnet-5-5` and
`No BedrockSharedCapacityRole available` (the SDK built the model from that ID), no failed model
call and none of the Bedrock error texts.

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
