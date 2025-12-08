"""Process utilities for spawning detached workers.

Provides cross-platform support for starting background processes
that are detached from the parent (MCP server) process.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def spawn_detached_dreamer(
    log_file: Path | None = None,
) -> bool:
    """Spawn the dream worker as a detached process.

    The worker will:
    1. Detach from the parent process (MCP server)
    2. Try to acquire a file lock
    3. Run consolidation tasks if lock is acquired
    4. Exit gracefully

    This function returns immediately without waiting for the worker.

    Args:
        log_file: Optional path to write worker logs.
                  If None, logs go to /dev/null (Unix) or NUL (Windows).

    Returns:
        True if the process was spawned successfully, False otherwise.
    """
    try:
        # Build command to run the dream worker module
        cmd = [sys.executable, "-m", "exocortex.worker.dream"]

        if sys.platform == "win32":
            # Windows: Use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
            # This creates a process that survives parent termination
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008

            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = 0  # SW_HIDE

            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a") as log:
                    subprocess.Popen(
                        cmd,
                        stdout=log,
                        stderr=log,
                        stdin=subprocess.DEVNULL,
                        creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                        startupinfo=startup_info,
                        close_fds=True,
                    )
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                    startupinfo=startup_info,
                    close_fds=True,
                )
        else:
            # Unix (macOS/Linux): Use start_new_session to create new process group
            # This makes the process independent of the parent's terminal session
            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a") as log:
                    subprocess.Popen(
                        cmd,
                        stdout=log,
                        stderr=log,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,
                        close_fds=True,
                    )
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )

        logger.info("Dream worker spawned successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to spawn dream worker: {e}")
        return False


def is_dreamer_running(lock_path: Path) -> bool:
    """Check if a dream worker is currently running.

    Args:
        lock_path: Path to the dream worker's lock file.

    Returns:
        True if a worker holds the lock, False otherwise.
    """
    from filelock import FileLock, Timeout

    if not lock_path.exists():
        return False

    # Try to acquire the lock with zero timeout
    lock = FileLock(lock_path, timeout=0)
    try:
        with lock:
            # If we got the lock, no worker is running
            return False
    except Timeout:
        # Lock is held by another process
        return True


def get_default_log_path() -> Path:
    """Get the default log path for the dream worker."""
    from ..config import get_config
    config = get_config()
    return config.data_dir / "logs" / "dream.log"

