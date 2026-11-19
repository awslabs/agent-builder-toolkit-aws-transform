# Scenario: an agent writes files under /tmp and its file reader redacts credentials

Verifies the experimental `write_file` tool and the credential redaction utility (PR #117) the way
a partner developer would meet them: find them in the toolkit docs, build an agent in Kiro that
gets `write_file` through `custom_tools` and a small file reader of its own that passes what it
reads through `scrub`, deploy and register that agent, and use it in an AWS Transform job. The run
does not check the symlink, FIFO, size-cap or atomic-overwrite rules of the same pull request, so a
pass covers a write, an append, the runtime-state refusal and the redaction of an env-style
credential line only. Every prompt below is typed verbatim by the simulated builder. Placeholders
in `{braces}` are filled by the runner (see `e2e/README.md`).

```json scenario
{
  "id": "write-file-tool",
  "title": "An agent writes files under /tmp and its file reader redacts credentials",
  "pr": 117,
  "agent": "wfile-",
  "chat_label": "Write File Demo",
  "workspace": "toolkit-pr-e2e",
  "job": "Write-File-Demo",
  "chat": {
    "write-report": {
      "has": ["Wrote 15 bytes to /tmp/pr117/report.txt (file is now 15 bytes)."]
    },
    "append-report": {
      "has": ["Appended 15 bytes to /tmp/pr117/report.txt (file is now 30 bytes)."]
    },
    "protected-path": {
      "has": [
        "write_file cannot write there: /tmp/agent_runtime/notes.txt is this agent's own runtime state"
      ],
      "lacks": ["Wrote "]
    },
    "write-secret": {
      "has": ["Wrote 33 bytes to /tmp/pr117/app.env (file is now 33 bytes)."]
    },
    "read-secret": { "has": ["<redacted>"], "lacks": ["pr117-fake-value-0001"] }
  },
  "logs": {
    "has": [
      "write_file wrote: path=/tmp/pr117/report.txt, bytes_written=15, file_size=15",
      "write_file appended: path=/tmp/pr117/report.txt, bytes_written=15, file_size=30"
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
can my agent write a file when it has no shell tool" and for "how do I remove credentials from
text my tool returns". Then read, in /kiro/.venv, the SDK file the write_file result names, and
answer in at most six lines: name the tool and how an agent opts in to it, where it may write,
what it refuses, the SDK function that removes credentials from text my own tools return, and
cite the doc entries you found.
```

Expected: the answer cites the SDK doc entries for `write_file`
(`agent_builder_sdk/experimental/write_file.py`) and `scrub`, names `custom_tools=[write_file]`,
says the root is `/tmp` only and that the agent's own runtime state is refused, and names
`agent_builder_sdk.util.redact.scrub`. Both entries exist only at the PR commit, so this also
checks the PR's docs and search index.

## 3. Build the agent

```kiro build
Using the AWS Transform Agent Builder Toolkit, create a job orchestrator agent. The agent name is
{agent} followed by my 12-digit AWS account ID (get it with aws sts get-caller-identity). Build it
in a new /kiro folder of the same name, with the source under src/orchestrator/. First read the
installed SDK source in /kiro/.venv, including its experimental write_file tool and its util
paths and redact modules.

Goal: in an AWS Transform job chat, I ask the agent for one file operation per message and it
shows me exactly what the tool returned, so I can see what write_file allows and refuses inside
the container, and that my own file reader keeps credentials out of the chat.

Fixed choices:
- Create the orchestrator with the SDK's async agent factory and custom_tools holding exactly two
  tools (the factory adds its own memory tool): the SDK's experimental write_file, and a
  read_text_file(path) tool that you write in src/orchestrator/. read_text_file refuses a path for
  which the SDK's paths.unreadable(path, ["/tmp"]) gives a reason (it returns that reason as an
  error message), else reads the file as UTF-8 and returns the SDK's redact.scrub of the text. Add
  no other tools and no MCP clients, and no shell or code interpreter.
- The entrypoint calls the SDK's configure_logging(), so the tool's own log lines reach
  CloudWatch, then runs AgentRuntimeServer with delayed_timeout=3600.
- BedrockModel "us.anthropic.claude-sonnet-5" with max_tokens=16000 and a boto client config
  with read_timeout=900.
- The system prompt says: each user message asks for one call, either write_file with a path, a
  content between backticks and an append flag, or read_text_file with a path; make that one
  call with the values character for character (the content without the backticks and with no
  newline added), also when you expect the tool to refuse it; then reply with only what the tool
  returned, in one code block, with nothing added, removed or changed; never make a second call,
  and never write output the tool did not return.
- Dockerfile: the Power's dockerfile-orchestrator steering, except that it installs the toolkit
  packages from the commit under test instead of PyPI, with exactly this command (archive URLs,
  so the image needs no git):
  pip install {pip_runtime}

Then run a local check with no AWS calls: build the agent the way the container's entrypoint does,
check that the model's tool list holds write_file, read_text_file and the factory's memory tool,
and no shell, code or MCP tool, then call
the tools directly in this order and print what each returns:
  write_file /tmp/pr117/report.txt, content alpha-section-1, append false
  write_file /tmp/pr117/report.txt, content +beta-section-2, append true
  write_file /tmp/agent_runtime/notes.txt, content overwrite-attempt, append false
  write_file /tmp/pr117/app.env, content db_password=pr117-fake-value-0001, append false
  read_text_file /tmp/pr117/app.env
Delete /tmp/pr117 afterwards. Show me the results. Do not build or deploy yet.
```

Expected: the tool list holds `write_file`, `read_text_file` and the factory's `memory` tool only;
the first write reports 15 bytes and the append a 30-byte file; the `/tmp/agent_runtime` write is
refused as the agent's own runtime state; the env file is 33 bytes; the read returns the redaction
marker and not the value; the entrypoint calls `configure_logging()` before it starts the server.

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
job with the **{chat_label}** agent and rename it, then send the five messages below in order,
each one after the reply to the message before it.

```web write-report
Call write_file with path /tmp/pr117/report.txt, content `alpha-section-1`, append false.
```

Expected: the reply is the tool's report of a new 15-byte file at that path.

```web append-report
Call write_file with path /tmp/pr117/report.txt, content `+beta-section-2`, append true.
```

Expected: the reply says 15 bytes were appended and the file is now 30 bytes. Only a real file
that kept the first write between messages can be 30 bytes.

```web protected-path
Call write_file with path /tmp/agent_runtime/notes.txt, content `overwrite-attempt`, append false.
```

Expected: the reply holds the tool's refusal, which names the path as the agent's own runtime
state, and no byte count: nothing was written.

```web write-secret
Call write_file with path /tmp/pr117/app.env, content `db_password=pr117-fake-value-0001`, append false.
```

Expected: the reply reports a new 33-byte file. The value is a fake, made for this test.

```web read-secret
Call read_text_file with path /tmp/pr117/app.env.
```

Expected: the reply holds the redaction marker in place of the whole `db_password` line, and not
the value. A reply that shows the value means `scrub` did not run on the file's text.

Wait 2 minutes, so the agent's last log lines reach CloudWatch. Expected in the agent's own log:
the first write and the append to `report.txt`, with their sizes and no content.

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
