"""Entry point for Exocortex MCP server."""

import logging
import sys

from .config import get_config
from .server import create_server


def setup_logging() -> None:
    """Configure logging to stderr (MCP protocol uses stdout)."""
    config = get_config()

    # MCP uses stdout for communication, so we log to stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    root_logger.addHandler(handler)


def main() -> None:
    """Main entry point for Exocortex."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Load configuration
    config = get_config()
    logger.info("Starting Exocortex MCP server...")
    logger.info(f"Data directory: {config.data_dir}")
    logger.info(f"Embedding model: {config.embedding_model}")

    # Ensure data directory exists
    config.ensure_data_dir()

    # Create and run server
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()

