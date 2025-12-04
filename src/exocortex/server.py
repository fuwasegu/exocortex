"""MCP Server definition for Exocortex."""

import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    "Exocortex",
    instructions=(
        "Exocortex is your external brain - a local MCP server that stores "
        "and retrieves development insights, technical decisions, and "
        "troubleshooting knowledge. Use store_memory to save new insights "
        "and recall_memories to find relevant past experiences."
    ),
)


@mcp.tool()
def ping() -> str:
    """Health check tool to verify Exocortex is running.

    Returns a simple message confirming the server is operational.
    """
    config = get_config()
    now = datetime.now(timezone.utc).isoformat()
    return (
        f"🧠 Exocortex is alive!\n"
        f"Time: {now}\n"
        f"Data directory: {config.data_dir}\n"
        f"Embedding model: {config.embedding_model}"
    )


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp

