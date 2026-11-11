# Scenario: an agent with heartbeat monitoring sends heartbeats to AWS Transform

Verifies heartbeat monitoring (PR #94) the way a partner developer would meet it: find it in the
toolkit docs, build an agent in Kiro, deploy it, register it with monitoring type HEARTBEAT, and
use it in an AWS Transform job while the SDK sends heartbeats. Every prompt below is typed
verbatim by the simulated builder. Placeholders in `{braces}` are filled by the runner (see
`e2e/README.md`).

```json scenario
{
  "id": "heartbeat-monitoring",
  "title": "An agent with heartbeat monitoring sends heartbeats to AWS Transform",
  "pr": 94,
  "agent": "hb-demo-",
  "chat_label": "Heartbeat Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Heartbeat-Demo",
  "chat": {
    "ask-total": { "has": ["245000"] },
    "ask-pair": { "has": ["125000"] }
  },
  "logs": {
    "has": [
      "Heartbeat monitoring enabled for agent",
      "Heartbeat service started (interval: 300s)",
      "Heartbeat sent successfully"
    ],
    "lacks": ["Heartbeat disabled", "Heartbeat failed"]
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
does my agent send a heartbeat to the platform". From the results, answer in at most six lines:
name the SDK class that sends the heartbeat and the monitoring type that turns it on, and cite
the doc entry you found.
```

Expected: the answer cites the SDK reference entry `HeartbeatService`
(`agent_builder_sdk/heartbeat/heartbeat_service.py`) and names the monitoring type `HEARTBEAT`.
That entry exists only at the PR commit, so this also checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its heartbeat module.

Goal: in an AWS Transform job chat, the agent answers questions about a fixed application
inventory. I will register it with heartbeat monitoring, so the SDK has to signal liveness while
the job runs, and I want to see that in the agent's log.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory. Add no tools and no MCP clients.
- Write no heartbeat code: AgentRuntimeServer starts the SDK's heartbeat service by itself.
- The entrypoint first calls the SDK's configure_logging() (agent_builder_sdk.logging_config), so
  the SDK's INFO log lines reach the runtime log, and then runs AgentRuntimeServer with
  delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt holds the inventory: payments-api (Java, 120000 lines of code), ledger-svc
  (.NET, 80000), portal-web (Node.js, 45000). It says: answer questions about the inventory in
  two sentences, never call a tool, and write every number in full, in digits.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint
does, and check that HeartbeatService imports from agent_builder_sdk.heartbeat, that the server
object has a heartbeat_service attribute, and that after the entrypoint's logging setup the
logger agent_builder_sdk.heartbeat is enabled for INFO. Run the check as a plain Python script,
not under pytest, and do not turn logging off in it: pytest adds its own log handlers, and then
the third check fails for a correct entrypoint. Show me the results. Do not build or deploy yet.
```

Expected: the local check passes all three checks. The entrypoint calls `configure_logging()`
before it creates the server, and the agent has no heartbeat code of its own.

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
  configuration["agentCard"]["capabilities"]["allowChatWhenJobTerminated"] = False and
  configuration["monitoringType"] = "HEARTBEAT" (the helper always sends HEALTHCHECK), and then
  calls the original.
- Call _pipeline._register_with_atx with agent_name, agent_version="1.0.0", runtime_arn,
  access_role_arn (the AWSTransformAgentInvokeRole ARN in this account), registry_endpoint=None,
  owner_contact_info (the owner contact above), job_orchestrator=True and
  chat_ui_label="{chat_label}". Print the result. If it isn't success: true, stop there and show
  me the error.

Then, read-only, in the same script: with registry_client from
agent_builder_mcp.tools.registry._client, poll get_agent_version for up to 2 minutes until
version 1.0.0 is ACTIVE, and show its jobOrchestrator, jobOrchestratorMetadata.chatUILabel and
configuration.monitoringType. Do not deregister or delete anything.
```

Expected: `success: true`, version 1.0.0 `ACTIVE`, jobOrchestrator `true`, chat UI label as above,
monitoring type `HEARTBEAT`.

## 6. Use it in AWS Transform

Sign in to the console, enable and open the AWS Transform web app, create the workspace, create a
job with the **{chat_label}** agent and rename it, then send:

```web ask-total
How many lines of code do the three applications have in total?
```

Expected (`chat`): the reply gives the total for the three applications.

After the reply, wait 9 minutes, then send the next message. Keep the job open and send nothing
in between. The SDK sends a heartbeat every 5 minutes, the first one 5 minutes after the agent
starts in the job. The wait covers the first heartbeat and keeps the job stop in step 7 away
from the next ones.

```web ask-pair
How many lines of code do ledger-svc and portal-web have together?
```

Expected (`chat`): the reply gives the sum for the two applications, so the agent still answers
after its first heartbeat. The replies do not prove the feature; the log does, so a log that
cannot be read is a failure.

Expected (`logs`): the agent's own log (CloudWatch, the runtime's log group) shows that the SDK
read monitoring type HEARTBEAT from AWS Transform, started its heartbeat service with the
300-second interval and sent a heartbeat. It shows no failed heartbeat and no
`Heartbeat disabled` line (that line means the SDK did not get HEARTBEAT from AWS Transform;
compare it with the read-back in step 5). A `Failed to check monitoring type` line is a note,
not a failure: the SDK repeats the lookup at the next heartbeat.

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
