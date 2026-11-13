# Scenario: an agent asks for the platform S3 connector to read a customer bucket

Verifies the platform connector tool and its docs (PR #103) the way a partner developer would meet
them: find the connector in the toolkit docs, build an agent in Kiro whose model gets the platform
tools, deploy and register that agent, and ask it in an AWS Transform job to read a file from the
user's bucket. The system prompt names no connector type and no connector tool, so the run shows
which tool the model picks from the tool descriptions. The run does not create or approve a
connector (that needs an IAM role in the user's account), so a pass covers the request for access
only, not the temporary credentials. Every prompt below is typed verbatim by the simulated builder.
Placeholders in `{braces}` are filled by the runner (see `e2e/README.md`).

```json scenario
{
  "id": "platform-connector",
  "title": "An agent asks for the platform S3 connector to read a customer bucket",
  "pr": 103,
  "agent": "s3conn-",
  "chat_label": "Connector Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Connector-Demo",
  "chat": {
    "ask-access": { "has": ["platform|s3|1"] }
  },
  "logs": {
    "has": ["\"connectorType\": \"platform|s3|1\"", "create_hitl_task_with_json_input: OUTPUT="],
    "lacks": [
      "\"connectorType\": \"mainframe_modernization|s3|1\"",
      "\"connectorType\": \"dotnet_modernization|s3|1\""
    ]
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
can my agent read files from a customer's S3 bucket". The search shows only the start of each
entry, so read the full text of the entries it finds. Then answer in at most six lines: name the
connector type that every agent can use, the tool that asks the user for that connector, and the
SDK class and method that return the temporary credentials, and cite the entries.
```

Expected: the answer names `platform|s3|1`, `create_platform_connector_hitl_task` and
`Connector.get_temporary_credentials_for_connector`, and cites the developer guide entry and the
SDK doc entry for `Connector` (`agent_builder_sdk/agentic_framework/connector.py`). Those entries
exist only at the PR commit, so this also checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv and the tools of the agentic MCP server installed there.

Goal: in an AWS Transform job chat, a user asks the agent to read a file from their own S3
bucket. The agent has no access to the user's account, so it asks for access with a connector
task and tells the user what it asked for.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory and pass it the MCP client that
  AgentRuntimeServer gives to the agent factory, so the model gets the platform tools. Add no
  custom tools and no other MCP clients.
- The entrypoint runs AgentRuntimeServer with delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- Use exactly this system prompt and add nothing to it. It must name no connector type and no
  connector tool, because the model has to choose the tool from the tool descriptions:
  "You get this agent access to the Amazon S3 bucket of the user. When the user asks you to
  read from their bucket, do these steps in order. 1. Call list_job_plan_steps. If the job has
  no step, call put_job_plan with mode override and one step named Connect the S3 bucket, then
  call list_job_plan_steps again. 2. Ask the user for access to the bucket: call one connector
  tool, once, with the id of that step. 3. Call no tool after that. Reply with only what that
  tool returned, one line for each field in the form name = value, with nothing added, removed
  or changed. If a tool returns an error, reply with the error text, word for word. Answer
  other questions in two sentences."
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls, with /kiro/.venv/bin/python: print the name and the
parameters of every tool of the agentic MCP server whose name holds "connector". Then call the
Python function of the platform connector tool for an S3 bucket, with a step id of your choice
and with the function that creates the task replaced by a stub, and print the JSON that the stub
received and what the tool returned. Show me the results. In every local check, stub the model
client and boto3: a local check must make no call to Amazon Bedrock or to any other AWS
service. Do not build or deploy yet.
```

Expected: two tools are listed, `create_platform_connector_hitl_task` (`step_id`, `connector`) and
`create_s3_connector_hitl_task` (`step_id`, `connector_type`); the stub received the component
`GeneralConnector`, blocking type `NON_BLOCKING` and a JSON input whose `properties.connector`
holds the connector type `platform|s3|1`, a required `s3BucketArn` field and an optional
`s3BucketKmsKeyArn` field; the tool returned the stub's result plus `connectorType`; the system
prompt in the source is the one above, word for word; the check made no AWS call.

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
job with the **{chat_label}** agent and rename it, then send the message below.

```web ask-access
I am the developer of this agent. Read the file report.csv from my S3 bucket. You have no
access to my AWS account, so ask me for it, and tell me what you asked for.
```

Expected: the reply holds the result of the tool, one field on each line, with
`connectorType = platform|s3|1` and the status of the task, and the job shows one task,
"Configure Amazon S3 connector". A result with no connector type means the model picked
`create_s3_connector_hitl_task`: agents that are not on the allowlist of its types then fail
when they ask for the credentials.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
the task payload with the platform connector type and the result of the task creation, and no
task payload with a workload-owned connector type.

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
