# Agent Builder MCP Server
# Agent Builder MCP Server

An [MCP](https://modelcontextprotocol.io/) server that gives [Kiro](https://kiro.dev/) the tools and knowledge it needs to build, deploy, and manage agents on [AWS Transform](https://aws.amazon.com/transform/).

With this server configured, Kiro gains first-class help for AWS Transform agent development: searching documentation, scaffolding agent code, deploying to AWS, and managing runtime operations.

Pair it with the [**AWS Transform Agent Builder Kiro Power**](https://kiro.dev/powers/) to unlock the full end-to-end experience — the Power provides curated steering rules and workflows that guide Kiro through the entire agent-building process on top of this server's tools.

## Installation

```bash
pip install agent-builder-mcp-aws-transform
```

This installs an `agent-builder-mcp` command that speaks MCP over stdio.

## Quick start

Add the server to Kiro's MCP configuration:

```json
{
  "mcpServers": {
    "agent-builder": {
      "command": "uvx",
      "args": ["agent-builder-mcp-aws-transform"]
    }
  }
}
```

Restart Kiro. It will now have access to the agent-builder tool set.

## What it provides

Tools are grouped into six categories:

- **Search** — retrieve documentation and examples from the bundled AWS Transform knowledge base (BM25 keyword search, no network calls, no embeddings).
- **Agent registry** — look up, register, and version agents.
- **Skill operations** — manage the skills an agent exposes.
- **Deployment** — package and deploy agents to AWS.
- **Validation** — check agent manifests and configurations before deployment.
- **CloudWatch** — query agent logs and metrics.

Ask Kiro "what agent-builder tools do you have?" and it will list the exact set available in your installed version.

## Requirements

- Python 3.11+
- AWS credentials configured (standard `boto3` credential chain) for deployment and CloudWatch tools. Search and validation work offline.

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
