"""OpenTelemetry session management for Base agents."""

import hashlib
import logging
import os
import uuid

from agent_builder_sdk.env_var import (
    ENV_KEY_AGENT_INSTANCE_ID,
    ENV_KEY_JOB_ID,
    ENV_KEY_WORKSPACE_ID,
)

logger = logging.getLogger(__name__)


def get_trace_attributes(service_name=None, session_id=None):
    """Get trace attributes for Strands agent."""
    if session_id is None:
        env_values = [
            os.getenv(ENV_KEY_WORKSPACE_ID),
            os.getenv(ENV_KEY_JOB_ID),
            os.getenv(ENV_KEY_AGENT_INSTANCE_ID),
        ]
        if any(val is None for val in env_values):
            session_id = str(uuid.uuid4())
            logger.info(
                f"tracing session.id is set as {session_id} because one or more environment variables [WORKSPACE_ID, JOB_ID, AGENT_INSTANCE_ID] are missing"
            )
        else:
            runtime_session_id = "_".join(env_values)  # type: ignore
            session_id = hashlib.sha256(runtime_session_id.encode("utf-8")).hexdigest()
            logger.info(
                f"tracing session.id is set as {session_id} for [workspaceId={env_values[0]},jobId={env_values[1]},agentInstanceId={env_values[2]}]"
            )
    else:
        logger.info(f"session.id is passed in: {session_id}")

    return {
        "session.id": session_id,
        "workspace.id": os.getenv("WORKSPACE_ID"),
        "job.id": os.getenv("JOB_ID"),
        "agent.instance.id": os.getenv("AGENT_INSTANCE_ID"),
        "service.name": service_name or "atx-agent",
    }
