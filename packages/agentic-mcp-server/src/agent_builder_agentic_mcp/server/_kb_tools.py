# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import logging
from typing import Any, Dict, Literal

from agent_builder_agentic_mcp.client import atx_agenticapi_client
from agent_builder_agentic_mcp.server._inject_qt_request_context import _inject_qt_request_context
from agent_builder_agentic_mcp.server._server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="/tmp/qt-mcp-server.log",  # Log to file to avoid interfering with stdio
)
logger = logging.getLogger(__name__)


# Knowledge Base Tools
@mcp.tool(
    name="retrieve_from_knowledge_base",
    description="Retrieves relevant information from a knowledge base using a search query. Supports scopes: AWS (general AWS knowledge) or PRODUCT (AWS Transform product specific knowledge)",
)
async def retrieve_from_knowledge_base(
    retrieval_query: str, retrieval_scope: Literal["AWS", "PRODUCT"]
) -> Dict[str, Any]:
    """
    Retrieves data from the knowledge base.

    Args:
        retrieval_query: The query to search for in the knowledge base.
        retrieval_scope: The scope to search within. Valid values: "AWS", "PRODUCT".

    Returns:
        The retrieved data from the knowledge base.
    """
    logger.info("Retrieving content from the knowledge base")
    try:
        client = atx_agenticapi_client()

        # Prepare the request parameters
        kwargs: Dict[str, Any] = {
            "retrievalQuery": {"text": retrieval_query},
            "retrievalScope": retrieval_scope,
        }

        # Make the API call
        response = client.retrieve_from_knowledge_base(**_inject_qt_request_context(kwargs))

        logger.info("Retrieved content from the knowledge base")

        retrieved_content = [result["content"] for result in response.get("retrievalResults", [])]

        # Return the retrieved data
        return {"retrieved_content": retrieved_content}
    except Exception as e:
        logger.error(f"Error retrieving from knowledge base: {str(e)}")
        raise
