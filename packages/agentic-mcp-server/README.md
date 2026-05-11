# Agent Builder Agentic MCP Server

An [MCP](https://modelcontextprotocol.io/) server that agents built with the [Agent Builder SDK](https://pypi.org/project/agent-builder-sdk-aws-transform/) use at runtime to talk to the [AWS Transform](https://aws.amazon.com/transform/) platform.

## Installation

```bash
pip install agent-builder-agentic-mcp-aws-transform
```

This installs an `agent-builder-agentic-mcp` command.

## Usage

### From the SDK (typical)

The SDK's `AgentRuntimeServer` spawns this MCP server automatically:

```python
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer

server = AgentRuntimeServer(
    agent_factory=my_factory,
    binary_location="agent-builder-agentic-mcp",  # the command installed by this package
    ...
)
server.start()
```

### Standalone (local testing)

```bash
agent-builder-agentic-mcp \
  --agenticApiEndpoint https://... \
  --workspaceId <workspace-id> \
  --jobId <job-id> \
  --agentInstanceId <agent-instance-id>
```

Run `agent-builder-agentic-mcp --help` for the full set of flags (transport, SSE host/port, custom auth token file, auto-refresh, etc.).

## Requirements

- Python 3.11+
- AWS credentials configured (standard `boto3` credential chain)
- A valid AWS Transform authorization token in `~/.aws/transform-credentials` (or specify with `--authTokenFile`)

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [NOTICE](NOTICE).
