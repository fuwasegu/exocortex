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


# =============================================================================
# Configuration & Path Functions
# =============================================================================


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


# =============================================================================
# Server Info Read/Write
# =============================================================================


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
            pid_str = pid_file.read_text().strip()
            if pid_str:
                return int(pid_str)
        except (ValueError, OSError):
            pass
    return None


# =============================================================================
# Process Verification
# =============================================================================


def is_exocortex_process(pid: int, port: int = 8765) -> bool:
    """Verify that the given PID is actually an Exocortex server process.

    This prevents killing unrelated processes that happen to have the same PID
    (e.g., after a system restart).

    Args:
        pid: Process ID to check.
        port: Port the server should be listening on.

    Returns:
        True if the process is an Exocortex server, False otherwise.
    """
    try:
        # Check if process exists
        os.kill(pid, 0)
    except OSError:
        return False

    # Try to verify the process is actually exocortex
    # Method 1: Check /proc/{pid}/cmdline on Linux
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.exists():
        try:
            cmdline = proc_cmdline.read_text()
            if "exocortex" in cmdline.lower():
                return True
            # Don't return False here - fall through to ps command
            # The cmdline might not contain "exocortex" in some cases
        except OSError:
            pass

    # Method 2: Use ps command (works on macOS and Linux)
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            cmdline = result.stdout.lower()
            if "exocortex" in cmdline:
                return True
            # If it's a python process, verify by checking if it's listening on our port
            if "python" in cmdline:
                return is_pid_listening_on_port(pid, port)
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # If we can't verify, be conservative and assume it's not ours
    logger.warning(f"Could not verify PID {pid} is an Exocortex process")
    return False


def is_pid_listening_on_port(pid: int, port: int) -> bool:
    """Check if a specific PID is listening on a specific port.

    Args:
        pid: Process ID to check.
        port: Port number to check.

    Returns:
        True if the PID is listening on the port.
    """
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            listening_pids = result.stdout.strip().split("\n")
            return str(pid) in listening_pids
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return False


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


# =============================================================================
# Process Management
# =============================================================================


def find_pid_on_port(port: int) -> int | None:
    """Find the PID of a process listening on the given port.

    Args:
        port: The port to check.

    Returns:
        PID if found, None otherwise.
    """
    try:
        # Use lsof to find process listening on port
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # May return multiple PIDs, take the first one
            pid_str = result.stdout.strip().split("\n")[0]
            return int(pid_str)
    except Exception as e:
        logger.debug(f"lsof failed: {e}")

    return None


def kill_old_server(port: int = 8765) -> bool:
    """Kill the old server process if running.

    This function includes safety checks to prevent killing unrelated processes
    that might have the same PID after a system restart.

    Args:
        port: The port the server should be listening on.

    Returns:
        True if server was killed or wasn't running, False on error.
    """
    pid = read_server_pid()
    from_pid_file = pid is not None

    if pid is None:
        # No PID file - try to find process by port (for old servers without PID tracking)
        pid = find_pid_on_port(port)
        if pid is None:
            logger.debug("No PID file and no process found on port")
            return True
        logger.info(f"Found process {pid} on port {port} (no PID file)")

    # Safety check: Verify the PID is actually an Exocortex process
    if not is_exocortex_process(pid, port):
        if from_pid_file:
            logger.warning(
                f"PID {pid} from server.pid is NOT an Exocortex process. "
                "Cleaning up stale PID file without killing."
            )
            cleanup_server_files()
            return True
        else:
            logger.warning(
                f"Process {pid} on port {port} is not Exocortex, skipping kill"
            )
            return False

    # Additional safety: Verify the process is listening on our port
    if not is_pid_listening_on_port(pid, port):
        logger.warning(
            f"PID {pid} is not listening on port {port}. "
            "Cleaning up stale PID file without killing."
        )
        cleanup_server_files()
        return True

    try:
        # Process verified, safe to kill
        logger.info(f"Killing old Exocortex server (PID: {pid}) for version upgrade...")
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
        time.sleep(0.5)
        cleanup_server_files()
        return True

    except OSError as e:
        # Process doesn't exist or permission denied
        logger.debug(f"Process {pid} not running or inaccessible: {e}")
        cleanup_server_files()
        return True
    except Exception as e:
        logger.error(f"Error killing old server: {e}")
        return False


# =============================================================================
# Server Lifecycle
# =============================================================================


def check_version_and_restart_if_needed(host: str, port: int) -> bool | None:
    """Check if server version matches client version, restart if not.

    This enables automatic server updates when the client code is updated.
    If version mismatch is detected, kills old server and starts new one immediately.

    Args:
        host: Server host.
        port: Server port.

    Returns:
        True if server is ready to use (existing or newly started).
        False if server needs to be started by caller.
        None on error.
    """
    if not is_server_running(host, port):
        return False  # Caller should start the server

    server_version = read_server_version()

    needs_restart = False

    if server_version is None:
        # Old server without version tracking, kill and restart
        logger.info("Server running without version info, restarting...")
        needs_restart = True
    elif server_version != __version__:
        logger.info(
            f"Version mismatch: server={server_version}, client={__version__}. "
            "Restarting server..."
        )
        needs_restart = True
    else:
        logger.info(f"Server version matches ({__version__})")
        return True  # Server is ready

    if needs_restart:
        if not kill_old_server(port):
            logger.error("Failed to kill old server")
            return None

        # Wait for port to be fully released
        for _ in range(10):
            time.sleep(0.5)
            if not is_server_running(host, port):
                break
        else:
            logger.warning("Port still in use after kill, attempting to continue...")

        # Start new server immediately to prevent other instances from starting old version
        logger.info("Starting new server with current version...")
        start_background_server(host, port)

        if not wait_for_server(host, port, timeout=15.0):
            logger.error("Failed to start new server after version upgrade")
            return None

        logger.info("New server started successfully")
        return True  # Server is ready

    return True


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


# =============================================================================
# Proxy Class
# =============================================================================


class StdioToSSEProxy:
    """Proxy that bridges stdio MCP protocol to an SSE server."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}/mcp/sse"
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


# =============================================================================
# Entry Points
# =============================================================================


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

    Uses file locking to prevent race conditions when multiple Cursor instances
    start simultaneously.
    """
    from filelock import FileLock, Timeout

    # Use a lock file to prevent race conditions
    lock_file = get_server_pid_file().with_suffix(".lock")
    lock = FileLock(lock_file, timeout=30)

    try:
        with lock:
            # Check version and restart if needed (handles kill + start)
            result = check_version_and_restart_if_needed(host, port)

            if result is None:
                logger.error("Version check failed")
                sys.exit(1)
            elif result is True:
                # Server is ready (existing or newly started after version upgrade)
                logger.info(f"Server ready on {host}:{port}")
            else:
                # result is False: no server running, need to start
                logger.info(f"Server not running on {host}:{port}, starting...")
                start_background_server(host, port)

                if not wait_for_server(host, port, timeout=15.0):
                    logger.error("Failed to start background server")
                    sys.exit(1)

                logger.info("Background server is ready")

    except Timeout:
        logger.warning(
            "Could not acquire lock for server management. "
            "Another instance may be starting the server."
        )
        # Wait a bit and hope the other instance started the server
        if not wait_for_server(host, port, timeout=20.0):
            logger.error("Server not available after waiting")
            sys.exit(1)

    # Run the proxy (outside the lock so multiple proxies can connect)
    run_proxy(host, port)
