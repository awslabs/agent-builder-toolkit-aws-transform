"""
Base agent implementation for the multi-agent system.

This module provides a base agent implementation that can be extended
by specialized agents in the system.
"""

import json
import logging
import traceback
from typing import Any, Dict, List, Optional

import boto3
from agent_builder_mcp_client import AsyncMCPClient
from typing_extensions import deprecated

from agent_builder_sdk import tool_use_prompts
from agent_builder_sdk._boto_client import create_bedrock_client
from agent_builder_sdk.tool import Tool

logger = logging.getLogger(__name__)


@deprecated("`Agent` is deprecated. Use `BaseOrchestrator` or `BaseSubagent` instead")
class Agent:
    """Base agent implementation."""

    # Define activity event type class attribute
    _activity_event_type: str = "agent_activity"

    def __init__(
        self,
        system_prompt: str,
        bedrock_model_id: str,
        mcp_client: Optional[AsyncMCPClient] = None,
        optimize_prompt_tooluse: bool = True,
        bedrock_region: str = "us-west-2",
        anthropic_version: str = "bedrock-2023-05-31",
        max_tokens: int = 4096,
        anthropic_beta: Optional[List[str]] = None,
        guardrail_identifier: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        session: Optional[boto3.Session] = None,
    ):
        """
        Initialize the agent.

        Args:
            system_prompt: System prompt for the agent
            bedrock_model_id: LLM model ID from Bedrock
            mcp_client: Optional MCP client for tool execution
            optimize_prompt_tooluse: Option to append tool use prompt to enhance agent's capabilities
            bedrock_region: AWS region for Bedrock client
            anthropic_version: Version of Anthropic API to use
            max_tokens: Maximum number of tokens in the response
            anthropic_beta: Beta features to enable in Anthropic API
            guardrail_identifier: The identifier for the guardrail to use
            guardrail_version: The version of the guardrail to use
            session: The boto3 session to use
        """
        self.system_prompt = system_prompt.strip() if system_prompt else ""
        self.model_id = bedrock_model_id
        if optimize_prompt_tooluse:
            self.system_prompt = tool_use_prompts.apply_tool_use_prompts(
                self.model_id, self.system_prompt
            )
        self.mcp_client = mcp_client

        # Store Claude configuration parameters
        self.bedrock_region = bedrock_region
        self.anthropic_version = anthropic_version
        self.max_tokens = max_tokens
        self.anthropic_beta = anthropic_beta or []

        logger.info(f"Agent initialized with {self.model_id} and {self.mcp_client}")

        self.mcp_prompts: Dict[str, str] = {}
        self.tools: List[Tool] = []
        self._messages: List[Dict[str, Any]] = []
        self._bedrock_runtime = create_bedrock_client(region=self.bedrock_region, session=session)
        self.guardrail_identifier = guardrail_identifier
        self.guardrail_version = guardrail_version

    def register_tool(self, tool: Tool) -> None:
        """
        Register a tool with the agent.

        Args:
            tool: Tool to register
        """
        self.tools.append(tool)
        logger.info(f"Registered tool: {tool.name}")

    def _create_mcp_tool_wrapper(self, tool_name: str):
        """
        Create a wrapper function for an MCP tool.

        Args:
            tool_name: Name of the MCP tool

        Returns:
            An async function that wraps the MCP tool call
        """

        async def tool_wrapper(input_data: Dict[str, Any]):
            if self.mcp_client:  # Add null check to satisfy mypy
                try:
                    tool_result = await self.mcp_client.call_tool(tool_name, **input_data)
                    logger.debug(f"tool_wrapper: tool_result={tool_result}")
                    result: Dict[str, Any] = {
                        "content": [],
                    }
                    if hasattr(tool_result, "isError") and tool_result.isError:
                        result["is_error"] = True
                    for content in tool_result.content:
                        if hasattr(content, "text"):
                            txt = content.text
                            result["content"].append({"type": "text", "text": txt})
                        else:
                            logger.warning(f"Unknown MCP response content type: {type(content)}")
                            result["content"].append({"type": "text", "text": str(content)})
                    return result
                except Exception as e:
                    logger.error(f"Error calling MCP tool {tool_name}: {e}")
                    return {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "is_error": True,
                    }
            else:
                return {"content": [], "is_error": True}

        return tool_wrapper

    async def register_mcp_tools(self) -> None:
        """
        Register tools from the MCP server.

        This method connects to the MCP server and registers all available tools.
        """
        if not self.mcp_client:
            logger.warning("No MCP client provided, skipping MCP tool registration")
            return

        try:
            # Get tool schemas from the MCP server
            tool_schemas = await self.mcp_client.get_tools()

            # Register each tool
            for schema in tool_schemas:
                tool_name = schema.name
                tool_description = schema.description or f"MCP tool: {tool_name}"
                tool_input_schema = schema.input_schema

                # Create a wrapper function using the helper method
                tool_wrapper = self._create_mcp_tool_wrapper(tool_name)

                # Register the tool
                self.register_tool(
                    Tool(
                        name=tool_name,
                        func=tool_wrapper,
                        input_schema=tool_input_schema,
                        description=tool_description,
                        is_mcp_tool=True,
                    )
                )

                logger.info(f"Registered MCP tool: {tool_name}")
        except Exception as e:
            logger.error(f"Error registering MCP tools: {str(e)}", exc_info=True)
            raise e

    async def shutdown(self):
        """Shutdown the agent."""
        logger.info("Shutting down agent")
        if self.mcp_client:
            await self.mcp_client.close()
        logger.info("Agent shutdown")

    async def invoke_claude(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Invoke Claude via AWS Bedrock.

        Args:
            messages: List of message objects in the format Claude expects
            tools: Optional list of tools to make available to Claude

        Returns:
            The complete response from Claude
        """
        try:
            # Ensure messages list is properly formatted - first message must be user
            if not messages:
                raise ValueError("No messages provided to invoke Claude")

            # Trim whitespace from all message content
            for message in messages:
                if isinstance(message.get("content"), str):
                    message["content"] = message["content"].strip()
                elif isinstance(message.get("content"), list):
                    for item in message["content"]:
                        if isinstance(item, dict) and "text" in item:
                            item["text"] = item["text"].strip()

            # Log the number of messages being sent
            logger.info(f"Invoking Claude with {len(messages)} messages")
            logger.debug(messages)

            # Prepare the request body
            request_body = {
                "anthropic_version": self.anthropic_version,
                "max_tokens": self.max_tokens,
                "messages": messages,
            }

            # inject system prompt if deined
            if self.system_prompt:
                request_body["system"] = self.system_prompt

            if self.guardrail_identifier and self.guardrail_version:
                request_body["guardrailConfig"] = {
                    "guardrailIdentifier": self.guardrail_identifier,
                    "guardrailVersion": self.guardrail_version,
                    "trace": "enabled",
                }

            # Add tools if provided
            if tools:
                request_body["tools"] = tools
                special_tools = [tool for tool in tools if "type" in tool]
                if special_tools and "computer-use-2024-10-22" not in self.anthropic_beta:
                    # Only add the beta feature if it's not already included
                    beta_features = self.anthropic_beta.copy()
                    beta_features.append("computer-use-2024-10-22")
                    request_body["anthropic_beta"] = beta_features
                elif self.anthropic_beta:
                    request_body["anthropic_beta"] = self.anthropic_beta

                logger.debug(
                    f"{len(tools)} tools ({len(special_tools)} special tools) provided: {tools}"
                )

            # Invoke the model
            response = self._bedrock_runtime.invoke_model(
                modelId=self.model_id, body=json.dumps(request_body)
            )

            # Parse the response
            response_body = json.loads(response.get("body").read())
            return response_body

        except Exception as e:
            logger.error(f"Error invoking Claude via Bedrock: {str(e)}")
            raise

    async def _format_tools_for_claude(self) -> List[Dict[str, Any]]:
        """
        Format tools for Claude's API.

        Returns:
            List of tool definitions in Claude's format
        """
        claude_tools = []

        for tool in self.tools:
            claude_tools.append(tool.to_dict())

        return claude_tools

    async def process(self, user_input: str) -> Dict[str, Any]:
        """
        Process a user request asynchronously.

        Args:
            user_input: User input to process

        Returns:
            Response from the agent
        """
        # Format tools for Claude
        claude_tools = await self._format_tools_for_claude()

        # Add user input to conversation history
        self._messages.append({"role": "user", "content": user_input})

        # Log the number of messages being sent to Claude
        logger.info(f"Invoking Claude with {len(self._messages)} messages")

        tool_name_invoked = None
        try:
            # Invoke Claude with the full conversation history
            response = await self.invoke_claude(self._messages, claude_tools)
            self._messages.append({"role": response["role"], "content": response["content"]})
            logger.debug(f"LLM Response from Claude: {response}")
            # Process tool calls if present
            while "stop_reason" in response and response["stop_reason"] == "tool_use":
                tool_calls = [c for c in response["content"] if c["type"] == "tool_use"]
                tool_call_content = []
                if len(tool_calls) > 1:
                    logger.warning(f"More than one tool call found: {tool_calls}")
                    tool_name_invoked = "Multiple"
                logger.info(f"Claude made {len(tool_calls)} tool calls of {tool_calls}")

                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_input = tool_call.get("input", {})
                    tool_id = tool_call.get("id")

                    logger.debug(
                        f"Processing tool call: {tool_name} with input: {json.dumps(tool_input)}"
                    )

                    # Find the tool
                    tool = next((t for t in self.tools if t.name == tool_name), None)
                    if tool:
                        # Call the tool
                        logger.info(f"Calling tool: {tool_name}::{tool.func.__name__}")
                        # if LLM calls multiple tools one after another, record the first tool
                        if tool_name_invoked != "Multiple" and tool_name_invoked is None:
                            tool_name_invoked = tool_name
                        elif tool_name_invoked is not None and tool_name_invoked != tool_name:
                            tool_name_invoked = "Multiple"

                        try:
                            tool_result = await tool(tool_input)
                            logger.debug(f"tool_result: {tool_result}")
                            content = tool_result["content"]

                            msg = {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": (
                                    content if isinstance(content, str) else json.dumps(content)
                                ),
                            }

                            if "is_error" in tool_result:
                                msg["is_error"] = tool_result["is_error"]

                            # Add the tool call and result to messages
                            tool_call_content.append(msg)

                        except Exception as e:
                            # Handle tool execution error
                            error_message = f"Error executing tool {tool_name}: {str(e)}"
                            logger.error(error_message)
                            logger.error(traceback.format_exc())
                            raise e

                # Add tool results to conversation history
                self._messages.append({"role": "user", "content": tool_call_content})

                # Get final response from Claude
                response = await self.invoke_claude(self._messages, claude_tools)
                logger.debug(f"LLM Response from Claude (within loop): {response}")
                self._messages.append({"role": response["role"], "content": response["content"]})

            response["tool_name_invoked"] = tool_name_invoked
            return response

        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            raise

    async def __call__(self, user_input: str) -> Dict[str, Any]:
        """
        Process a user request (async version).

        Args:
            user_input: User input to process

        Returns:
            Response from the agent
        """
        return await self.process(user_input)
