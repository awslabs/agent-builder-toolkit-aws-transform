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

## Streaming (opt-in)

By default an orchestrator serves one turn at a time through a buffered queue, and `message/stream` is rejected. Pass a `StreamingConfig` to stream turns live over SSE (reasoning, tool calls and text) and to serve many users of the same job concurrently:

```python
from agent_builder_sdk.streaming.config import StreamingConfig

server = AgentRuntimeServer(
    agent_factory=agent_factory,
    host="0.0.0.0",
    port=8080,
    binary_location="agent-builder-agentic-mcp",
    storage_dir="/tmp/my_agent",
    # Omit or pass None to keep streaming off (the default).
    streaming_config=StreamingConfig(
        agent_idle_ttl_seconds=30 * 60,  # optional; evict idle per-user agents
        emit_reasoning=True,             # optional; stream and persist reasoning (default True)
        emit_tool_calls=True,            # optional; stream and persist tool calls (default True)
    ),
)
```

The `simple_cli_agent_core.py` entry point exposes the same option as `--concurrent-streaming` (plus `--emit-reasoning/--no-emit-reasoning` and `--emit-tool-calls/--no-emit-tool-calls`). AWS Transform only streams to agents whose agent card declares `capabilities.streaming: true`.

**How it works**: Strands runs one invocation at a time per `Agent`, so the server keeps a `StreamingAgentPool` with one agent per source (a user, or another agent that streams to yours). Agents are built on first use and evicted after `agent_idle_ttl_seconds`. Your factory runs once per source, so each pooled agent builds its own model client. The MCP client, the conversation repository and the `MemoryManager` stay shared, so a user's buffered and streamed turns see the same job history. A synchronous factory runs on a dedicated worker thread, one build at a time, so building a new user's agent does not stall live streams; it has no running event loop there. Each streamed final response is persisted back to the chat.

**Concurrency contract**: with streaming on, several users' turns run concurrently on one event loop. Tools and hooks must not keep per-request state in module-level or class-level mutable globals; use a `contextvars.ContextVar` or the per-request `ToolContext` / `invocation_state` instead.

**Factory requirement**: your agent factory must accept and forward `conversation_repository` and `memory_manager` (for example `def agent_factory(mcp_client, storage_dir, **kwargs)` passing both to `create_default_orchestrator`). The server checks this at startup.

**Subagents**: an agent that inherits `StreamingCapable` can stream too (`simple_subagent_cli.py --concurrent-streaming` builds one). Two opt-in tools, added through `custom_tools`, use a subagent's stream:

- `send_message_to_subagent_and_relay` streams the subagent's answer live to the user as the orchestrator's final answer, and ends the turn.
- `stream_message_to_subagent` returns the subagent's answer (its last model cycle) to the orchestrator without streaming it to the user, like `send_message_to_subagent`.

**History repair**: when a turn is interrupted (timeout, client disconnect, crash), the next history load gives the unanswered message a placeholder reply, so the next turn answers its own prompt. A turn ended by a terminating tool (`stop_event_loop`) stores its `force_stop_response` as the reply.

## Requirements

- Python 3.11+
- AWS credentials configured (standard `boto3` credential chain), with Bedrock access for model inference
- The `agent-builder-agentic-mcp` binary on disk — see [agent-builder-agentic-mcp-aws-transform](https://pypi.org/project/agent-builder-agentic-mcp-aws-transform/)
- **Calling other AWS Transform agents**: Your AWS account must be allowlisted for the [AWS Transform composability initiative](https://aws.amazon.com/transform/partners/). Contact your Partner Development Manager (PDM) or apply through AWS Partner Central.

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
