"""Proxy module for stdio-to-SSE bridging."""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = await self._handle_request(request)
                    if response is not None:
                        response_str = json.dumps(response)
                        print(response_str, flush=True)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON: {e}")
                except Exception as e:
                    logger.error(f"Error handling request: {e}")

            except Exception as e:
                logger.error(f"Proxy read error: {e}")
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
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "prompts": {},
                    "resources": {},
                },
                "serverInfo": {
                    "name": "exocortex-proxy",
                    "version": "0.1.0",
                },
            }
        elif method == "initialized":
            return {}
        elif method == "tools/list":
            tools_result = await session.list_tools()
            return {"tools": [t.model_dump() for t in tools_result.tools]}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            call_result = await session.call_tool(tool_name, tool_args)
            return call_result.model_dump()
        elif method == "prompts/list":
            prompts_result = await session.list_prompts()
            return {"prompts": [p.model_dump() for p in prompts_result.prompts]}
        elif method == "prompts/get":
            prompt_name = params.get("name", "")
            prompt_args = params.get("arguments", {})
            prompt_result = await session.get_prompt(prompt_name, prompt_args)
            return prompt_result.model_dump()
        elif method == "resources/list":
            resources_result = await session.list_resources()
            return {"resources": [r.model_dump() for r in resources_result.resources]}
        elif method == "resources/read":
            uri = params.get("uri", "")
            resource_result = await session.read_resource(uri)
            return resource_result.model_dump()
        elif method == "ping":
            return {}
        elif method == "notifications/cancelled":
            return None
        else:
            logger.warning(f"Unknown method: {method}")
            raise ValueError(f"Method not found: {method}")


def run_proxy(host: str, port: int) -> None:
    """Run the stdio-to-SSE proxy."""
    proxy = StdioToSSEProxy(host, port)
    proxy.run()


def ensure_server_and_run_proxy(host: str, port: int) -> None:
    """Ensure the SSE server is running and then run the proxy."""
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
