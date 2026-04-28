import asyncio
import json
import typing


class Tool:
    """Tool implementation that follows Claude's tool use specification."""

    def __init__(
        self,
        name: str,
        func: typing.Callable,
        description: str = "",
        input_schema: typing.Optional[typing.Dict[str, typing.Any]] = None,
        special_schema_less_tool_definition: typing.Optional[typing.Dict[str, typing.Any]] = None,
        is_mcp_tool: bool = False,
    ):
        """
        Initialize the tool.

        Args:
            name: Name of the tool
            func: Function to call when the tool is invoked
            description: Description of the tool
            input_schema: Schema of the input
            is_mcp_tool: Whether this tool is an MCP tool
        """
        self.name = name
        self.func = func
        self.description = description.strip() if description else ""
        self.input_schema = input_schema or {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "Input for the tool"}},
            "required": ["input"],
        }
        # Special schema for tools model trained with
        # https://docs.anthropic.com/en/docs/agents-and-tools/computer-use#combine-computer-use-with-other-tools
        self.special_schema_less_tool_definition = special_schema_less_tool_definition
        self.is_mcp_tool = is_mcp_tool

    async def __call__(self, input_data: typing.Dict[str, typing.Any]) -> typing.Any:
        """
        Call the tool function with the provided input data.

        Args:
            input_data: The input data for the tool

        Returns:
            The result of the function call
        """
        # Handle string input case for backward compatibility
        if isinstance(input_data, str):
            input_data = {"input": input_data}

        # Check if input is just {"input": string} and the function expects more params
        if list(input_data.keys()) == ["input"] and isinstance(input_data["input"], str):
            # Try to parse input as JSON if it looks like a JSON string
            try:
                if input_data["input"].strip().startswith("{") and input_data[
                    "input"
                ].strip().endswith("}"):
                    parsed_input = json.loads(input_data["input"])
                    if isinstance(parsed_input, typing.Dict):
                        input_data = parsed_input
            except (json.JSONDecodeError, ValueError):
                # If we can't parse it, just use as is
                pass

        if asyncio.iscoroutinefunction(self.func):
            return await self.func(input_data)
        else:
            return self.func(input_data)

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        """
        Convert the tool to a typing.Dictionary format compatible with Claude's tool use.

        Returns:
            typing.Dictionary representation of the tool
        """
        # handle special tools with model training
        if self.special_schema_less_tool_definition:
            return self.special_schema_less_tool_definition

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
