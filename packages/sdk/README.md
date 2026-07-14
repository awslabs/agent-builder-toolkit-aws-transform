# Agent Builder SDK

A Python SDK for building agents that run on [AWS Transform](https://aws.amazon.com/transform/).

Use it to build two kinds of agents:

- **Orchestrator agents** — stateful, conversational agents that drive a workflow end-to-end and can delegate to subagents.
- **Subagents** — stateless, task-focused agents invoked by an orchestrator to handle a single unit of work (e.g., a code generation, a validation, a review step).

The SDK wraps the common concerns — HTTP server, request routing, agent lifecycle, checkpointing, A2A protocol extensions, authentication, metrics, and tracing — so you focus on the agent's behavior instead of the plumbing.

## Installation

```bash
pip install agent-builder-sdk-aws-transform
```

Or install everything (SDK + runtime + dev tools):

```bash
pip install agent-builder-sdk-aws-transform[full]
```

## Building an orchestrator

### 1. Create your orchestrator class

```python
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator


class MyCustomOrchestrator(AsyncBaseOrchestrator):
    """Your custom orchestrator implementation."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt="You are a specialized orchestrator for...",
            **kwargs
        )
        # Add your custom tools, hooks, conversation implementation
```

### 2. Create custom tools (optional)

Define domain-specific tools using Strands decorators:

```python
from strands.tools import tool


@tool
def my_custom_tool(param: str) -> str:
    """Your custom tool description."""
    return f"Processed: {param}"
```

See the [Strands custom tools documentation](https://strandsagents.com/docs/user-guide/concepts/tools/custom-tools/) for more.

### 3. Create your entry point

Use `AgentRuntimeServer` with a custom agent factory. The server is compatible with both Bedrock AgentCore runtime protocols and AWS Transform agentic compute endpoints.

```python
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.agent_factory import create_default_orchestrator


def main():
    def agent_factory(mcp_client, storage_dir):
        return create_default_orchestrator(
            mcp_client=mcp_client,
            storage_dir=storage_dir,
            system_prompt="Your custom system prompt here",
            with_base_guardrails=True,  # Enable built-in guardrails (optional)
        )

    server = AgentRuntimeServer(
        agent_factory=agent_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
        storage_dir="/tmp/my_agent",
        checkpoint_strategy="conversation",  # optional, enables checkpointing
        checkpoint_interval=10,              # optional, enables checkpointing
    )
    server.start()


if __name__ == "__main__":
    main()
```

**Base guardrails**: Set `with_base_guardrails=True` to enable built-in system prompt protections that:

- Decline job / job plan / artifact / workspace deletion requests
- Decline prompt injection or requests that reveal the agent's architecture
- Decline PII information requests
- Decline requests unrelated to transformation

**Custom agent initialization**: Extend `AgentRuntimeServer` and override `_get_agent_params` to pass additional arguments to your factory. See `_get_agent_params` in `agent_runtime_server.py` for the defaults.

## Building a subagent

### 1. Create your subagent class

```python
from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent


class MyCustomSubagent(AsyncBaseSubagent):
    """Your custom subagent implementation."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt="You are a specialized subagent for...",
            **kwargs
        )
```

### 2. Create your entry point

`StatelessAgentRuntimeServer` is well-suited for subagents since it handles requests without persistent state. You can also use `AgentRuntimeServer` for subagents if you need persistent state or queue-based processing.

```python
from agent_builder_sdk.server.stateless_agent_runtime_server import StatelessAgentRuntimeServer
from agent_builder_sdk.agent_factory import create_default_subagent


def main():
    def agent_factory(mcp_client):
        return create_default_subagent(
            mcp_client=mcp_client,
            system_prompt="Your custom subagent system prompt here",
            custom_tools=[my_custom_tool],  # Optional
        )

    server = StatelessAgentRuntimeServer(
        agent_factory=agent_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
    )
    server.start()


if __name__ == "__main__":
    main()
```

## Requirements

- Python 3.11+
- AWS credentials configured (standard `boto3` credential chain), with Bedrock access for model inference
- The `agent-builder-agentic-mcp` binary on disk — see [agent-builder-agentic-mcp-aws-transform](https://pypi.org/project/agent-builder-agentic-mcp-aws-transform/)
- **Calling other AWS Transform agents**: Your AWS account must be allowlisted for the [AWS Transform composability initiative](https://aws.amazon.com/transform/partners/). Contact your Partner Development Manager (PDM) or apply through AWS Partner Central.

## Configuration

### Agentic API Endpoint

The SDK communicates with the AWS Transform Agentic API, which requires explicit endpoint routing. The `get_agentic_api_client()` factory reads the `QT_AGENTIC_API_ENDPOINT` environment variable.

In managed compute (Bedrock AgentCore, MDE), this variable is injected automatically. For local development, set it explicitly:

```bash
export QT_AGENTIC_API_ENDPOINT=https://iad.prod.agenticapi.elastic-gumby.ai.aws.dev
```

| Stage | Region | Endpoint |
|-------|--------|----------|
| prod | us-east-1 | `https://iad.prod.agenticapi.elastic-gumby.ai.aws.dev` |
| prod | eu-central-1 | `https://fra.prod.agenticapi.elastic-gumby.ai.aws.dev` |
| gamma | us-east-1 | `https://iad.gamma.agenticapi.elastic-gumby.ai.aws.dev` |
| gamma | us-west-2 | `https://pdx.gamma.agenticapi.elastic-gumby.ai.aws.dev` |

### Development Flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `ATX_USE_MOCK_REGISTRY` | `false` | When `true`, `discover_subagents` returns fixture data without calling the API |

## Registry Schema Reference

When calling `PublishAgentVersion`, the configuration includes nested structures:

```
configuration
├── computeConfiguration
│   └── provisionedComputeConfiguration
│       ├── mdeConfiguration { atxAccessRoleArn, bootstrapRoleArn, environmentRoleArn, storageSize, devfile, instanceType }
│       └── agentCoreConfiguration { atxAccessRoleArn, runtimeArn, qualifier }
├── agentResiliencyConfiguration
│   ├── partnerControllerRetryWindowMinutes
│   └── agentRecoveryConfiguration { recoveryWaitTimeSeconds }
├── stopAgentConfiguration {}
├── inputPayloadSchema (JSON Schema)
├── outputPayloadSchema (JSON Schema)
├── agentCard { name, description, version, url, skills[], capabilities{extensions[]}, provider{} }
├── monitoringType (HEARTBEAT | HEALTHCHECK)
├── notificationsEnabled (ENABLED | DISABLED)
├── objectiveNegotiationPrompt
└── shortDescription
```

All of these are represented by dataclasses in `agent_builder_sdk.custom_types.agent_registry_types`.

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
