# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging

logger = logging.getLogger(__name__)

# https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview#chain-of-thought-tool-use
# To prompt Sonnet or Haiku to better assess the user query before making tool calls, the following prompt can be used
CLAUDE_PROMPT = r"""
Answer the user's request using relevant tools (if they are available). Before calling a tool, do some analysis within <thinking></thinking> tags. First, think about which of the provided tools is the relevant tool to answer the user's request. Second, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value. If all of the required parameters are present or can be reasonably inferred, close the thinking tag and proceed with the tool call. BUT, if one of the values for a required parameter is missing, DO NOT invoke the function (not even with fillers for the missing params) and instead, ask the user to provide the missing parameters. DO NOT ask for more information on optional parameters if it is not provided.
""".strip()

_MODEL_PROVIDER_CLAUDE = "claude"
_MODEL_KEYWORD_SONNET = "sonnet"


def apply_tool_use_prompts(model_id: str, prompt: str) -> str:
    """
    Apply tool use prompts to the given prompt.

    Args:
        prompt: The prompt to apply tool use prompts to

    Returns:
        The prompt with tool use prompts applied
    """
    if _MODEL_PROVIDER_CLAUDE in model_id.lower():
        if CLAUDE_PROMPT not in prompt:
            logger.info(f"Applying Claude tool use prompts to {model_id}'s prompt")
            return f"{prompt}\n\n{CLAUDE_PROMPT}"
    return prompt
