"""Proxy module for stdio-to-SSE bridging."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__

logger = logging.getLogger(__name__)


def get_server_version_file() -> Path:
    """Get the path to the server version file."""
    from .config import get_config

    config = get_config()
    return config.data_dir / "server_version"


def get_server_pid_file() -> Path:
    """Get the path to the server PID file."""
    from .config import get_config

    config = get_config()
    return config.data_dir / "server.pid"


def read_server_version() -> str | None:
    """Read the version of the currently running server."""
    version_file = get_server_version_file()
    if version_file.exists():
        try:
            return version_file.read_text().strip()
        except Exception:
            return None
    return None


def read_server_pid() -> int | None:
    """Read the PID of the currently running server."""
    pid_file = get_server_pid_file()
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except Exception:
            return None
    return None


def write_server_info(pid: int) -> None:
    """Write server version and PID files."""
    version_file = get_server_version_file()
    pid_file = get_server_pid_file()

    # Ensure parent directory exists
    version_file.parent.mkdir(parents=True, exist_ok=True)

    version_file.write_text(__version__)
    pid_file.write_text(str(pid))


def cleanup_server_files() -> None:
    """Remove server version and PID files."""
    for f in [get_server_version_file(), get_server_pid_file()]:
        with contextlib.suppress(Exception):
            f.unlink(missing_ok=True)


def kill_old_server() -> bool:
    """Kill the old server process if running.

    Returns:
        True if server was killed or wasn't running, False on error.
    """
    pid = read_server_pid()
    if pid is None:
        return True

    try:
        # Check if process exists
        os.kill(pid, 0)
        # Process exists, kill it
        logger.info(f"Killing old server (PID: {pid}) for version upgrade...")
        os.kill(pid, signal.SIGTERM)

        # Wait for process to terminate
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except OSError:
                # Process terminated
                cleanup_server_files()
                logger.info("Old server terminated successfully")
                return True

        # Force kill if still running
        logger.warning("Server didn't terminate gracefully, force killing...")
        os.kill(pid, signal.SIGKILL)
        cleanup_server_files()
        return True

    except OSError:
        # Process doesn't exist
        cleanup_server_files()
        return True
    except Exception as e:
        logger.error(f"Error killing old server: {e}")
        return False


def check_version_and_restart_if_needed(host: str, port: int) -> None:
    """Check if server version matches client version, restart if not.

    This enables automatic server updates when the client code is updated.
    """
    if not is_server_running(host, port):
        return

    server_version = read_server_version()

    if server_version is None:
        # Old server without version tracking, kill and restart
        logger.info("Server running without version info, restarting...")
        kill_old_server()
        # Wait for port to be released
        time.sleep(1)
        return

    if server_version != __version__:
        logger.info(
            f"Version mismatch: server={server_version}, client={__version__}. "
            "Restarting server..."
        )
        kill_old_server()
        # Wait for port to be released
        time.sleep(1)
    else:
        logger.info(f"Server version matches ({__version__})")


def is_server_running(host: str, port: int) -> bool:
    """Check if the SSE server is running on the specified port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait for the server to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_running(host, port):
            return True
        time.sleep(0.5)
    return False


def start_background_server(host: str, port: int) -> subprocess.Popen | None:
    """Start the SSE server in the background."""
    logger.info(f"Starting background SSE server on {host}:{port}...")
    logger.info(f"Server version: {__version__}")

    # Get the path to this module's directory
    module_dir = Path(__file__).parent.parent

    # Build the command to start the server
    cmd = [
        sys.executable,
        "-m",
        "exocortex.main",
        "--transport",
        "sse",
        "--host",
        host,
        "--port",
        str(port),
    ]

    try:
        # Start the server as a detached background process
        process = subprocess.Popen(
            cmd,
            cwd=str(module_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process
        )
        logger.info(f"Background server started with PID {process.pid}")

        # Write version and PID for future version checks
        write_server_info(process.pid)

        return process
    except Exception as e:
        logger.error(f"Failed to start background server: {e}")
        return None


class StdioToSSEProxy:
    """Proxy that bridges stdio MCP protocol to an SSE server."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}/sse"
        self._session = None
        self._read_stream = None
        self._write_stream = None

    def run(self) -> None:
        """Run the proxy, reading from stdin and writing to stdout."""
        import asyncio

        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async main loop for the proxy."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        logger.info(f"Connecting to SSE server at {self.server_url}")

        try:
            async with (
                sse_client(self.server_url) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                logger.info("Connected to SSE server")

                self._session = session

                # Process stdin in a thread to avoid blocking
                await self._process_stdio()

        except Exception as e:
            logger.error(f"Proxy error: {e}")
            raise

    async def _process_stdio(self) -> None:
        """Process stdin/stdout synchronously."""
        import asyncio

        loop = asyncio.get_event_loop()

        while True:
            try:
                # Read line from stdin in thread pool
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    logger.info("EOF received, exiting")
                    break

                line = line.strip()
                if not line:
                    continue

                logger.debug(f"Received: {line[:200]}...")

                try:
                    request = json.loads(line)
                    logger.info(
                        f"Processing method: {request.get('method', 'unknown')}"
                    )
                    response = await self._handle_request(request)
                    if response is not None:
                        response_str = json.dumps(response)
                        logger.debug(f"Response: {response_str[:200]}...")
                        print(response_str, flush=True)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON: {e}, line: {line[:100]}")
                except Exception as e:
                    logger.error(f"Error handling request: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Proxy read error: {e}", exc_info=True)
                break

    async def _handle_request(self, request: dict) -> dict | None:
        """Handle a JSON-RPC request by forwarding to the session."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            result = await self._dispatch_method(method, params)

            if request_id is not None:
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            return None

        except Exception as e:
            logger.error(f"Error calling method {method}: {e}")
            if request_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32603, "message": str(e)},
                }
            return None

    async def _dispatch_method(self, method: str, params: dict) -> Any:
        """Dispatch method to appropriate handler."""
        session = self._session

        if method == "initialize":
            # Return capabilities that indicate tools/prompts/resources are available
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "prompts": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": True},
                },
                "serverInfo": {
                    "name": "exocortex",
                    "version": __version__,
                },
            }
        elif method == "initialized":
            return {}
        elif method == "tools/list":
            tools_result = await session.list_tools()
            # Exclude None values to avoid Cursor validation errors
            return {
                "tools": [t.model_dump(exclude_none=True) for t in tools_result.tools]
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            call_result = await session.call_tool(tool_name, tool_args)
            return call_result.model_dump(exclude_none=True)
        elif method == "prompts/list":
            prompts_result = await session.list_prompts()
            return {
                "prompts": [
                    p.model_dump(exclude_none=True) for p in prompts_result.prompts
                ]
            }
        elif method == "prompts/get":
            prompt_name = params.get("name", "")
            prompt_args = params.get("arguments", {})
            prompt_result = await session.get_prompt(prompt_name, prompt_args)
            return prompt_result.model_dump(exclude_none=True)
        elif method == "resources/list":
            resources_result = await session.list_resources()
            return {
                "resources": [
                    r.model_dump(exclude_none=True) for r in resources_result.resources
                ]
            }
        elif method == "resources/read":
            uri = params.get("uri", "")
            resource_result = await session.read_resource(uri)
            return resource_result.model_dump(exclude_none=True)
        elif method == "ping":
            return {}
        elif method in ("notifications/cancelled", "notifications/initialized"):
            # Notifications don't need a response
            return None
        else:
            logger.warning(f"Unknown method: {method}")
            raise ValueError(f"Method not found: {method}")


def run_proxy(host: str, port: int) -> None:
    """Run the stdio-to-SSE proxy."""
    proxy = StdioToSSEProxy(host, port)
    proxy.run()


def ensure_server_and_run_proxy(host: str, port: int) -> None:
    """Ensure the SSE server is running with correct version and then run the proxy.

    This function:
    1. Checks if server is running
    2. If running, checks if version matches
    3. If version mismatch, kills old server and starts new one
    4. If not running, starts new server
    5. Runs the proxy
    """
    # Check version and restart if needed (handles kill + cleanup)
    check_version_and_restart_if_needed(host, port)

    if not is_server_running(host, port):
        logger.info(f"Server not running on {host}:{port}, starting...")
        start_background_server(host, port)

        if not wait_for_server(host, port, timeout=15.0):
            logger.error("Failed to start background server")
            sys.exit(1)

        logger.info("Background server is ready")
    else:
        logger.info(f"Server already running on {host}:{port}")

    # Run the proxy
    run_proxy(host, port)
