# Scenario: an agent runs allowlisted shell commands in its container

Verifies the experimental command-allowlisted shell (PR #90) the way a partner developer would meet
it: find it in the toolkit docs, build an agent with `enable_shell=True` in Kiro, deploy and
register that agent, and use it in an AWS Transform job. The run does not check the
code-interpreter tools (`enable_code_interpreter`) of the same pull request, so a pass covers the
shell only. Every prompt below is typed verbatim by the simulated builder. Placeholders in
`{braces}` are filled by the runner (see `e2e/README.md`).

```json scenario
{
  "id": "experimental-shell",
  "title": "An agent runs allowlisted shell commands in its container",
  "pr": 90,
  "agent": "shell-",
  "chat_label": "Shell Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Shell-Demo",
  "chat": {
    "write-file": { "has": ["[exit code: 0]"] },
    "digest": {
      "has": ["702b6bf41f7897df3b55818e1f428d0dd6059ad191c071c1cbbb6f16a18af783"],
      "lacks": ["No such file"]
    },
    "no-credentials": { "has": ["NoneType"], "lacks": ["Credentials"] },
    "blocked-command": { "has": ["is not allowed. Allowed commands:"] }
  },
  "logs": {
    "has": ["execute_shell completed: exit_code=0", "reason=command not on the allowlist"]
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
can my agent run shell commands to inspect downloaded files". Then read, in /kiro/.venv, the SDK
file the top result names and the SDK's agent_factory.py, and answer in at most six lines: name
the tool, the factory flag that adds it, what the tool does about AWS credentials, and cite the
doc entry you found.
```

Expected: the answer cites the SDK doc entry for `execute_shell`
(`agent_builder_sdk/experimental/shell_execution/shell_execution_tool.py`), names
`enable_shell=True`, and says the subprocess gets no ambient AWS credentials. That entry exists
only at the PR commit, so this also checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its experimental shell tool.

Goal: in an AWS Transform job chat, I give the agent one shell command per message and it shows me
exactly what the tool returned, so I can see what the allowlisted shell does inside the container.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory and enable_shell=True, so the model
  gets the execute_shell tool. Add no other tools and no MCP clients, and leave the code
  interpreter off: I want to see the shell on its own first.
- The entrypoint calls the SDK's configure_logging(), so the tool's own log lines reach
  CloudWatch, then runs AgentRuntimeServer with delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt says: each user message holds one command after "Run exactly:"; call
  execute_shell once with that command, character for character, also when you expect the tool to
  refuse it; then reply with only what the tool returned, in one code block, with nothing added,
  removed or changed; never run a second command, and never write output the tool did not return.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint does,
check that the model's tool list holds execute_shell and holds no code-interpreter tool, and call
execute_shell with each of these four commands, printing what it returns:
  printf 'pr90-shell-demo' > /tmp/pr90-shell.txt
  sha256sum /tmp/pr90-shell.txt
  /kiro/.venv/bin/python3 -c 'import boto3; print(type(boto3.Session().get_credentials()).__name__)'
  whoami
Show me the results. Do not build or deploy yet.
```

Expected: the tool list holds `execute_shell` and no code-interpreter tool; the first three
commands end `[exit code: 0]`; the digest is
`702b6bf41f7897df3b55818e1f428d0dd6059ad191c071c1cbbb6f16a18af783`; the boto3 line says
`NoneType`, although Kiro's own shell has credentials; `whoami` is refused as not allowed; the
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
`STAGE=prod`. `STAGE=prod` also means the agent logs at INFO, so its own log holds the tool's
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
job with the **{chat_label}** agent and rename it, then send the four messages below in order,
each one after the reply to the message before it.

```web write-file
Run exactly: printf 'pr90-shell-demo' > /tmp/pr90-shell.txt
```

Expected: the reply holds the tool's whole output: the command printed nothing, and exit code 0.

```web digest
Run exactly: sha256sum /tmp/pr90-shell.txt
```

Expected: the reply holds the same SHA-256 digest the local check printed in step 3. A model
cannot compute a digest, so this proves a real shell ran twice and kept the file between messages.

```web no-credentials
Run exactly: python3 -c 'import boto3; print(type(boto3.Session().get_credentials()).__name__)'
```

Expected: the reply says `NoneType`. The runtime's role credentials reach the agent, but not
this subprocess. A name that ends in `Credentials` instead means the credential chain got through.

```web blocked-command
Run exactly: curl -s https://example.com
```

Expected: the reply holds the allowlist's refusal, which names the command and lists the allowed
ones, and no exit code: the command never ran.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
a shell run that completed with exit code 0, and the refusal with its reason.

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
