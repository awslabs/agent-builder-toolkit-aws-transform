# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Application-wide constants for the AWS Transform Platform Base Agent.
"""

import logging

logger = logging.getLogger(__name__)

# Tool filtering constants
DEFAULT_SUBAGENT_EXCLUDED_TOOLS = [
    # Agent tools
    "invoke_agent",
    # Job tools
    "put_job_plan",
    "update_job_status",
    "delete_job_plan_step",
]

# Terminal stop reasons that mean a guardrail blocked the turn. Bedrock surfaces these on the
# result's stop_reason; in Strands 1.45 they are NOT exceptions or force-stops — the event loop
# falls straight through to a normal EventLoopStopEvent (only max_tokens raises, only tool_use
# branches). "content_filtered" is the model-provider content filter; "guardrail_intervened" is an
# applied Bedrock Guardrail. On a block, Bedrock returns its mandatory (min length 1)
# blockedOutputsMessaging as the response text, so the streaming path treats a block like a normal
# final turn — the block message streams and persists as the final response, no special handling.
GUARDRAIL_STOP_REASONS = ("guardrail_intervened", "content_filtered")

# Timeouts for an A2A message/send (MessageHandler.send_message). Streaming and notifications do not
# use them.
#
# The platform gives each SendMessage attempt to the agent 29s. The agent waits up to
# the send-message timeout for the turn. In queued mode (AgentRuntimeServer) it then replies with an
# acknowledgment and delivers the result later. In direct mode (StatelessAgentRuntimeServer) it
# cancels the turn and replies that it could not respond in time. Either reply sent at 28s reaches the
# platform inside the 29s attempt with a 1s buffer. A longer timeout means the platform cuts the call
# off before that reply arrives, so the sender sees a failure instead. The default stays 28s for
# backward compatibility, and a longer configured value is kept with a warning.
MAX_SEND_MESSAGE_TIMEOUT_SECONDS = 28
DEFAULT_SEND_MESSAGE_TIMEOUT_SECONDS = 28
# How long the agent keeps waiting for the turn after the acknowledgment, before it gives up on the
# delayed reply.
DEFAULT_SEND_MESSAGE_DELAYED_TIMEOUT_SECONDS = 300


def validate_send_message_timeout(timeout: int) -> int:
    """Return ``timeout``, logging a warning if it exceeds MAX_SEND_MESSAGE_TIMEOUT_SECONDS.

    The value is kept as configured so existing agents keep working. A value above the maximum means
    the platform can cut the call off before the agent's acknowledgment arrives.
    """
    if timeout > MAX_SEND_MESSAGE_TIMEOUT_SECONDS:
        logger.warning(
            "Send-message timeout %ss exceeds the maximum of %ss: the platform limits each SendMessage "
            "attempt to 29s, so a turn that runs past %ss can have its acknowledgment cut off and the "
            "sender sees a failure. Set the timeout to %s or less.",
            timeout,
            MAX_SEND_MESSAGE_TIMEOUT_SECONDS,
            MAX_SEND_MESSAGE_TIMEOUT_SECONDS,
            MAX_SEND_MESSAGE_TIMEOUT_SECONDS,
        )
    return timeout
