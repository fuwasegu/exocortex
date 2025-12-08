"""Main entry point for Exocortex MCP server."""

from __future__ import annotations

import argparse
import atexit
import logging
import os
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


def register_server_cleanup(config) -> None:
    """Register cleanup handlers for server files on exit.

    This ensures PID and version files are cleaned up when the server
    exits normally, preventing stale PID issues.
    """
    from . import __version__

    pid_file = config.data_dir / "server.pid"
    version_file = config.data_dir / "server_version"

    def cleanup():
        """Remove server PID and version files on exit."""
        logger = logging.getLogger(__name__)
        logger.info("Server shutting down, cleaning up...")

        for f in [pid_file, version_file]:
            try:
                if f.exists():
                    f.unlink()
                    logger.debug(f"Removed {f}")
            except OSError as e:
                logger.warning(f"Failed to remove {f}: {e}")

    # Register cleanup on normal exit
    atexit.register(cleanup)

    # Write PID and version files
    config.data_dir.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    version_file.write_text(__version__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Exocortex MCP Server - Your external brain for development insights"
    )
    parser.add_argument(
        "--mode",
        choices=["server", "proxy"],
        default="server",
        help="Run mode: 'server' runs the MCP server directly, "
        "'proxy' bridges stdio to a shared SSE server (default: server)",
    )
    parser.add_argument(
        "--ensure-server",
        action="store_true",
        help="In proxy mode, automatically start the SSE server if not running",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="Transport mode for server mode (default: from env or stdio)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to (default: from env or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (default: from env or 8765)",
    )
    return parser.parse_args()


def run_server_mode(
    transport: str, host: str, port: int, config, logger: logging.Logger
) -> None:
    """Run the MCP server directly."""
    logger.info(f"Transport: {transport}")

    if transport == "stdio":
        mcp.run()
    elif transport in ("sse", "streamable-http"):
        logger.info(f"Server URL: http://{host}:{port}/sse")

        # Register cleanup for PID/version files (for proxy mode auto-update)
        register_server_cleanup(config)

        # Configure host and port via settings
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport=transport)
    else:
        logger.error(f"Unknown transport: {transport}")
        sys.exit(1)


def run_proxy_mode(
    host: str, port: int, ensure_server: bool, logger: logging.Logger
) -> None:
    """Run in proxy mode, bridging stdio to SSE server."""
    from .proxy import ensure_server_and_run_proxy, is_server_running, run_proxy

    logger.info(f"Running in proxy mode, connecting to {host}:{port}")

    if ensure_server:
        ensure_server_and_run_proxy(host, port)
    else:
        if not is_server_running(host, port):
            logger.error(
                f"SSE server not running on {host}:{port}. "
                "Start it first or use --ensure-server"
            )
            sys.exit(1)
        run_proxy(host, port)


def main() -> None:
    """Run the Exocortex MCP server."""
    setup_logging()
    logger = logging.getLogger(__name__)

    args = parse_args()
    config = get_config()

    # CLI args override config/env
    host = args.host or config.server_host
    port = args.port or config.server_port

    logger.info("Starting Exocortex MCP")
    logger.info(f"Data directory: {config.data_dir}")
    logger.info(f"Embedding model: {config.embedding_model}")
    logger.info(f"Mode: {args.mode}")

    if args.mode == "proxy":
        run_proxy_mode(host, port, args.ensure_server, logger)
    else:
        transport = args.transport or config.server_transport
        run_server_mode(transport, host, port, config, logger)


if __name__ == "__main__":
    main()
