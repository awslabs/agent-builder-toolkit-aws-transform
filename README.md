# Agent Builder Toolkit for AWS Transform

[![sdk downloads](https://static.pepy.tech/personalized-badge/agent-builder-sdk-aws-transform?period=total&units=none&left_color=grey&right_color=blue&left_text=sdk%20downloads)](https://pepy.tech/projects/agent-builder-sdk-aws-transform)
[![mcp-server downloads](https://static.pepy.tech/personalized-badge/agent-builder-mcp-aws-transform?period=total&units=none&left_color=grey&right_color=blue&left_text=mcp-server%20downloads)](https://pepy.tech/projects/agent-builder-mcp-aws-transform)

Build custom agents for [AWS Transform](https://aws.amazon.com/transform/). The agent builder toolkit enables AWS Partners and customers to build agents tailored to their specific modernization needs that work within AWS Transform.

## Getting Started

### Install via Kiro (recommended)

The fastest way to get started is through the **[AWS Transform Agent Toolkit](https://kiro.dev/powers/#aws-transform-agent-toolkit)** Kiro Power, which provides guided agent development with documentation search, deployment automation, and registration tools.

1. Open the Kiro marketplace (Powers panel)
2. Search for **"AWS Transform Agent Toolkit"**
3. Choose **Install** to add the power to your Kiro environment

### Install via pip

Install the agent SDK and runtime dependencies:

```bash
pip install agent-builder-sdk-aws-transform agent-builder-agentic-mcp-aws-transform
```

Install the development MCP server for documentation search, deployment automation, and registry tools:

```bash
pip install agent-builder-mcp-aws-transform
```

## Capabilities

- **Agent scaffolding** — orchestrator and subagent templates with best practices
- **Citation-backed documentation search** — AWS Transform developer guide, SDK, and API specs
- **One-command deployment** — build container → push to ECR → deploy to Bedrock AgentCore → register with AWS Transform
- **IAM role templates** — CloudFormation for required roles
- **Cross-platform support** — Windows, macOS, and Linux

## Packages

### Agent SDK (runtime)

These packages are used by your agent at runtime:

| Package | PyPI | Description |
|---------|------|-------------|
| [sdk](packages/sdk) | [`agent-builder-sdk-aws-transform`](https://pypi.org/project/agent-builder-sdk-aws-transform/) | Base agent SDK for building orchestrators and subagents |
| [agentic-mcp-server](packages/agentic-mcp-server) | [`agent-builder-agentic-mcp-aws-transform`](https://pypi.org/project/agent-builder-agentic-mcp-aws-transform/) | MCP server that agents use at runtime to communicate with AWS Transform |
| [mcp-client](packages/mcp-client) | [`agent-builder-mcp-client-aws-transform`](https://pypi.org/project/agent-builder-mcp-client-aws-transform/) | Python MCP client for agent-to-agent communication |
| [types](packages/types) | [`agent-builder-types-aws-transform`](https://pypi.org/project/agent-builder-types-aws-transform/) | Shared type definitions |

### Developer tools

Used during development for documentation search, deployment, and registry management:

| Package | PyPI | Description |
|---------|------|-------------|
| [mcp-server](packages/mcp-server) | [`agent-builder-mcp-aws-transform`](https://pypi.org/project/agent-builder-mcp-aws-transform/) | MCP server with tools for documentation search, agent deployment, and registry operations |

## Learn More

- [AWS Transform](https://aws.amazon.com/transform/)
- [AWS Transform Partners](https://aws.amazon.com/transform/partners/)

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.
