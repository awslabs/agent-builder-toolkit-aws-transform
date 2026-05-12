# Agent Builder Types

Type annotations (PEP 561 stubs) for the [boto3](https://pypi.org/project/boto3/) client of the AWS Transform Agentic service.

Install this alongside `boto3` and your type checker (mypy, pyright, Pylance) and IDE will give you full autocomplete and type checking on calls to the AWS Transform Agentic service client — method signatures, request/response shapes, and paginators.

## Installation

```bash
pip install agent-builder-types-aws-transform
```

## Usage

No import or code change required. Once installed, your type checker picks up the stubs automatically:

```python
import boto3

# Your IDE now knows the full shape of this client.
client = boto3.client("awstransformagenticservice")

# Autocomplete works on method names and arguments.
response = client.list_agents(...)
```

For explicit annotations, you can import type defs directly:

```python
from agent_builder_types import TransformAgenticServiceClient
from agent_builder_types.type_defs import GetAgentInstanceResponseTypeDef

client: TransformAgenticServiceClient = boto3.client("awstransformagenticservice")
response: GetAgentInstanceResponseTypeDef = client.get_agent_instance(...)
```

## Requirements

- Python 3.11+
- `boto3 >= 1.28`

## License

Apache-2.0. See [LICENSE](LICENSE.txt) and [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
