import logging
from pathlib import Path

from anyio import run
from mcp.server.fastmcp import FastMCP

from agent_builder_mcp.tools.agent import register_agent_tools
from agent_builder_mcp.tools.cloudwatch import register_cloudwatch_tools
from agent_builder_mcp.tools.deployment import register_deployment_tools
from agent_builder_mcp.tools.diagnosis import register_diagnosis_tools
from agent_builder_mcp.tools.search import register_search_tools
from agent_builder_mcp.tools.skill_operations import register_skill_operations_tools
from agent_builder_mcp.tools.validation import register_validation_tools
from agent_builder_mcp.utils import get_package_version


def setup_logging(log_file: str | None, verbose: bool) -> None:
    """Configure logging to file (not stdout/stderr to avoid MCP conflicts)."""
    if not log_file:
        logging.disable(logging.CRITICAL)
        return

    log_path = Path(log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename=str(log_path),
        filemode="a",
    )

    logger = logging.getLogger(__name__)
    logger.info(f"=== ATX Agent Builder MCP Server starting (verbose={verbose}) ===")


async def run_server() -> None:
    """Run the MCP server."""
    logger = logging.getLogger(__name__)
    logger.info("Initializing FastMCP server")

    mcp = FastMCP(
        name="atx-agent-builder-mcp",
        instructions="ATX Agent Builder MCP Server - documentation search, agent deployment, registry operations, and platform management",
    )

    mcp._mcp_server.version = get_package_version()

    register_search_tools(mcp)
    register_deployment_tools(mcp)
    register_agent_tools(mcp)
    register_skill_operations_tools(mcp)
    register_diagnosis_tools(mcp)
    register_validation_tools(mcp)
    register_cloudwatch_tools(mcp)

    logger.info("All tools registered, starting stdio transport")
    await mcp.run_stdio_async()


def main(log_file: str | None = None, verbose: bool = False) -> None:
    """Entry point for the MCP server."""
    setup_logging(log_file, verbose)
    run(run_server)
