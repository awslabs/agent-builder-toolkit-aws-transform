# Agent Builder MCP Server

An [MCP](https://modelcontextprotocol.io/) server that provides tools and knowledge for building, deploying, and managing agents on [AWS Transform](https://aws.amazon.com/transform/).

This server works with any MCP-compatible client — [Kiro](https://kiro.dev/), Claude Code, Cursor, Windsurf, or any other IDE/tool that supports the Model Context Protocol.

## Installation

```bash
pip install agent-builder-mcp-aws-transform
```

This installs an `agent-builder-mcp` command that speaks MCP over stdio.

## Quick start

### With Kiro (recommended)

Install the [**AWS Transform Agent Toolkit**](https://kiro.dev/powers/#aws-transform-agent-toolkit) Kiro Power for the full guided experience — it configures this MCP server automatically and adds steering rules that guide Kiro through the entire agent-building process.

### With any MCP client

Add the server to your MCP configuration:

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

Restart your IDE/tool. It will now have access to the agent-builder tool set.

## What it provides

Tools are grouped into six categories:

- **Search** — retrieve documentation and examples from the bundled AWS Transform knowledge base (BM25 keyword search, no network calls, no embeddings).
- **Agent registry** — look up, register, and version agents.
- **Skill operations** — manage the skills an agent exposes.
- **Deployment** — package and deploy agents to AWS.
- **Validation** — check agent manifests and configurations before deployment.
- **CloudWatch** — query agent logs and metrics.

## Requirements

- Python 3.11+
- AWS credentials configured (standard `boto3` credential chain) for deployment and CloudWatch tools. Search and validation work offline.

## Development

### Retrieval benchmark

The bundled BM25 search is gated by a quality benchmark (48 golden queries across 6 categories):

```bash
pip install -e .
python bench/eval_retrieval.py
```

CI enforces **Recall@5 >= 0.70** and **MRR >= 0.60**. Current: Recall@5 = 0.80, MRR = 0.85.

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
