"""Main entry point for Exocortex MCP server."""

from __future__ import annotations

import logging
import sys

from .config import get_config
from .server import mcp


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    """Run the Exocortex MCP server."""
    setup_logging()
    logger = logging.getLogger(__name__)

    config = get_config()
    logger.info("Starting Exocortex MCP server")
    logger.info(f"Data directory: {config.data_dir}")
    logger.info(f"Embedding model: {config.embedding_model}")

    mcp.run()


if __name__ == "__main__":
    main()
