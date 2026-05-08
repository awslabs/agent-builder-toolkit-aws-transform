# Agent Builder MCP Client

An async Python client for talking to [MCP](https://modelcontextprotocol.io/) servers, used by the [Agent Builder SDK](https://pypi.org/project/agent-builder-sdk-aws-transform/) to invoke tools exposed over MCP.

Use it from any Python code that needs to call MCP tools — for example, an agent runtime that talks to one or more MCP servers.

## Installation

```bash
pip install agent-builder-mcp-client-aws-transform
```

## Quick start

```python
import asyncio
from agent_builder_mcp_client import AsyncMCPClient


async def main():
    client = AsyncMCPClient()

    # Connect over stdio (local server process)
    await client.connect_via_stdio(command="agent-builder-mcp")

    # Or connect over SSE (remote server)
    # await client.connect_via_sse(server_url="https://example.com/mcp")

    # Inspect the tools the server exposes
    for tool in client.tools:
        print(tool.name, tool.description)


asyncio.run(main())
```

## Transports

- **stdio** — launch and talk to a local MCP server subprocess.
- **SSE** — connect to a remote MCP server over HTTP with server-sent events, including optional custom headers for auth.

## Requirements

- Python 3.11+

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
