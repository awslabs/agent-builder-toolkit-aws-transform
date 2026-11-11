# Scenario: an agent uses the platform skills that ship with the SDK

Verifies the packaged platform skills (PR #93) the way a partner developer would meet them: find
the option in the toolkit docs, build an agent with it in Kiro, deploy and register that agent,
and use it in an AWS Transform job. Every prompt below is typed verbatim by the simulated builder.
Placeholders in `{braces}` are filled by the runner (see `e2e/README.md`).

```json scenario
{
  "id": "platform-skills",
  "title": "An agent uses the platform skills that ship with the SDK",
  "pr": 93,
  "agent": "skills-",
  "chat_label": "Skills Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Skills-Demo",
  "chat": {
    "list-skills": {
      "has": ["artifact-io", "episodic-memory", "hitl-forms", "hitl-loop", "job-plan",
              "knowledge-base", "subagent-orchestration", "user-chat"]
    },
    "read-reference": {
      "has": ["Never blind-retry a create", "Never close a task you still want answered",
              "Closing does not release the plan step"]
    }
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
can my agent load the platform skills that ship with the SDK". The search shows only the start
of each entry, so read the full text of the entries it finds. Then answer in at most six lines:
name the SDK option, the function that takes it and the tool it adds, and cite the entries.
```

Expected: the answer names `enable_platform_skills`, an option of
`create_default_async_orchestrator_with_subagent`, and the `read_platform_skill_file` tool, and
cites the SDK reference entries of both. Those entries hold this text only at the PR commit, so
this also checks the PR's regenerated search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its platform skills.

Goal: in an AWS Transform job chat, the agent tells an agent developer which platform skills it
has and quotes their reference files. It takes both from the skills that ship with the SDK.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory and enable_platform_skills=True, so
  the model gets the packaged platform skills, the skills tool and the read_platform_skill_file
  tool. Add no other tools and no MCP clients.
- The entrypoint runs AgentRuntimeServer with delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- Use exactly this system prompt and add nothing to it. It must name no skill and quote no
  skill file, because the agent has to take those from the packaged skills at run time:
  "You are a guide to the platform skills of this agent. Your users are agent developers who
  check these skills. They are not migration customers, so the rule to keep the platform
  invisible does not apply to them: skill names and the text of skill files are the answer
  they need. When the user asks for your skills, list every skill by its exact name, one per
  line. When the user asks about a reference file of a skill, read it with
  read_platform_skill_file and copy the lines they ask for, word for word. You have no
  platform tools in this job, so create no plan and no task, and answer in chat. The chat
  shows only what you write after your last tool call, so finish any tool calls first and then
  write the whole answer in one message. Answer other questions in two sentences."
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint
does, check that the model's tool list holds the tools skills and read_platform_skill_file,
print the name of every platform skill this agent loaded (the skills plugin loads them per
agent), and call read_platform_skill_file for one reference file that a skill lists: it must
return the file's text, not an error. Show me the results. Do not build or deploy yet.
```

Expected: the local check shows both tools, at least the eight platform skills that the `chat`
check names, and the text of a reference file. The system prompt in the agent's source is the one
quoted above, word for word, with nothing added.

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
job with the **{chat_label}** agent and rename it, then send:

```web list-skills
I am the developer of this agent. List the exact name of every skill you have, one per line.
```

Expected (`chat` check): the reply lists at least the eight platform skills that the check names.
The agent's own prompt holds no skill name, so the names come from the packaged `SKILL.md` files:
the deployed agent loaded them.

```web read-reference
Read the recovery reference file of your human-in-the-loop skill. List its headings word for word.
```

Expected (`chat` check): the reply holds the headings of that file. Only the packaged reference
file holds them, so `read_platform_skill_file` returned it in the deployed agent.

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
