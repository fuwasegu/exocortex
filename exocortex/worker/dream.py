"""Dream Worker - Background consolidation process for Exocortex.

This module implements the "Sleep" mechanism that runs in the background
to organize and consolidate the knowledge graph. It performs:

1. Deduplication: Detect and link highly similar memories
2. Orphan Rescue: Find and link isolated memories
3. Pattern Mining: Extract patterns from frequently accessed topics (Phase 2)

The worker is designed to run as a detached process, acquiring a file lock
to ensure exclusive database access when the user is not actively working.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout

from ..config import Config, get_config
from ..container import Container
from ..domain.models import RelationType

# Configure logging for the worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DreamWorker:
    """Background worker for knowledge graph consolidation.

    Implements the "Sleep" mechanism that:
    - Waits for database lock (user idle)
    - Performs consolidation tasks
    - Releases lock and exits
    """

    def __init__(
        self,
        config: Config | None = None,
        lock_timeout: float = 5.0,
        max_runtime: float = 300.0,
        check_server: bool = True,
    ) -> None:
        """Initialize the dream worker.

        Args:
            config: Exocortex configuration. Uses default if not provided.
            lock_timeout: Seconds to wait for lock acquisition.
            max_runtime: Maximum seconds to run before exiting.
            check_server: If True, check if SSE server is running and warn.
        """
        self.config = config or get_config()
        self.lock_timeout = lock_timeout
        self.max_runtime = max_runtime
        self.check_server = check_server
        self._running = False
        self._container: Container | None = None

        # Lock file location (worker-to-worker coordination)
        self.lock_path = self.config.data_dir / "dream.lock"

        # KùzuDB's internal lock file location
        self._kuzu_lock_path = self.config.data_dir / self.config.db_name / ".lock"

        # Configure signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False

    def _get_container(self) -> Container:
        """Get or create the DI container."""
        if self._container is None:
            self._container = Container(self.config)
        return self._container

    def _is_sse_server_likely_running(self) -> bool:
        """Check if SSE server is likely running.

        Uses socket check on default port. Not 100% reliable but provides
        a safety hint.

        Returns:
            True if server appears to be running.
        """
        import socket

        # Default SSE server port
        port = 8765

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                result = s.connect_ex(("localhost", port))
                return result == 0
        except Exception:
            return False

    def _is_kuzu_locked(self) -> bool:
        """Check if KùzuDB's internal lock file exists.

        KùzuDB creates a .lock file when a connection is open.
        This is a hint, not a guarantee of lock state.

        Returns:
            True if lock file exists.
        """
        return self._kuzu_lock_path.exists()

    def run(self) -> None:
        """Main entry point for the dream worker.

        Attempts to acquire the lock and run consolidation tasks.
        If lock cannot be acquired, exits gracefully.

        Safety checks:
        1. Warns if SSE server appears to be running
        2. Checks KùzuDB's internal lock file
        3. Uses file lock for worker-to-worker coordination
        """
        logger.info("Dream worker starting...")
        logger.info(f"Data directory: {self.config.data_dir}")
        logger.info(f"Lock file: {self.lock_path}")

        # Safety check 1: Warn about SSE server
        if self.check_server and self._is_sse_server_likely_running():
            logger.warning(
                "⚠️  SSE server may be running. "
                "Database access conflicts are possible. "
                "Consider running when server is idle or stopped."
            )
            # Continue anyway, but with warning logged

        # Safety check 2: Check KùzuDB internal lock
        if self._is_kuzu_locked():
            logger.warning(
                "⚠️  KùzuDB lock file exists. "
                "Another process may have the database open. "
                "Will attempt to proceed but may fail."
            )

        # Ensure data directory exists
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(self.lock_path, timeout=self.lock_timeout)

        try:
            with lock:
                logger.info("Lock acquired, starting consolidation...")
                self._running = True
                start_time = time.time()

                self._run_consolidation_tasks()

                elapsed = time.time() - start_time
                logger.info(f"Consolidation completed in {elapsed:.2f}s")

        except Timeout:
            logger.info(
                "Could not acquire lock (database in use). "
                "Will retry next time."
            )
        except Exception as e:
            logger.exception(f"Dream worker error: {e}")
        finally:
            self._cleanup()

    def _run_consolidation_tasks(self) -> None:
        """Execute all consolidation tasks."""
        if not self._running:
            return

        container = self._get_container()

        # Task 1: Deduplication
        logger.info("Task 1: Checking for duplicates...")
        self._task_deduplication(container)

        if not self._running:
            return

        # Task 2: Orphan Rescue
        logger.info("Task 2: Rescuing orphan memories...")
        self._task_orphan_rescue(container)

        if not self._running:
            return

        # Task 3: Pattern Mining (Phase 2 - placeholder)
        logger.info("Task 3: Pattern mining (placeholder for Phase 2)...")
        # self._task_pattern_mining(container)

    def _task_deduplication(self, container: Container) -> None:
        """Find and handle duplicate/near-duplicate memories.

        Memories with similarity >= 0.95 are flagged as potential duplicates.

        SAFETY: We use 'RELATED' relation with a clear reason instead of
        'SUPERSEDES' to avoid automatically asserting that one memory
        replaces another. Users can review and upgrade to SUPERSEDES if needed.
        """
        repo = container.repository
        service = container.memory_service

        try:
            # Get all memories
            memories, total, _ = repo.list_memories(limit=1000)
            logger.info(f"Checking {total} memories for duplicates...")

            duplicate_threshold = 0.95
            processed_pairs: set[tuple[str, str]] = set()
            duplicates_found = 0

            for i, memory in enumerate(memories):
                if not self._running:
                    break

                # Search for similar memories
                similar = repo.search_similar_by_embedding(
                    embedding=repo._embedding_engine.embed(memory.content),
                    limit=5,
                    exclude_id=memory.id,
                )

                for other_id, _, similarity, _, _ in similar:
                    if similarity < duplicate_threshold:
                        continue

                    # Create ordered pair to avoid duplicate processing
                    pair = tuple(sorted([memory.id, other_id]))
                    if pair in processed_pairs:
                        continue
                    processed_pairs.add(pair)

                    # Get the other memory
                    other = repo.get_by_id(other_id)
                    if other is None:
                        continue

                    # Determine which is newer for context in reason
                    if memory.created_at > other.created_at:
                        newer_id, older_id = memory.id, other.id
                        direction = "newer→older"
                    else:
                        newer_id, older_id = other.id, memory.id
                        direction = "older→newer"

                    # Create RELATED link instead of SUPERSEDES for safety
                    # User can manually upgrade to SUPERSEDES if appropriate
                    try:
                        service.link_memories(
                            source_id=newer_id,
                            target_id=older_id,
                            relation_type=RelationType.RELATED,
                            reason=(
                                f"⚠️ POTENTIAL_DUPLICATE (similarity: {similarity:.2%}, {direction}). "
                                "Review and consider using 'supersedes' if this is truly a duplicate."
                            ),
                        )
                        duplicates_found += 1
                        logger.info(
                            f"Flagged potential duplicate: {newer_id[:8]}... ↔ {older_id[:8]}... "
                            f"(similarity: {similarity:.2%})"
                        )
                    except Exception as e:
                        logger.debug(f"Could not link duplicates: {e}")

            logger.info(f"Deduplication complete: {duplicates_found} potential duplicates flagged")

        except Exception as e:
            logger.warning(f"Deduplication task error: {e}")

    def _task_orphan_rescue(self, container: Container) -> None:
        """Find orphan memories and suggest links.

        Orphans are memories with no tags and no links.
        We find the most similar non-orphan memory and create a weak link.
        """
        repo = container.repository
        service = container.memory_service

        try:
            # Get orphan memories (returns list of (id, summary) tuples)
            orphan_tuples = repo.get_orphan_memories()
            logger.info(f"Found {len(orphan_tuples)} orphan memories")

            rescued = 0
            for orphan_id, orphan_summary in orphan_tuples:
                if not self._running:
                    break

                # Get the full memory to access content for embedding
                memory = repo.get_by_id(orphan_id)
                if memory is None:
                    logger.debug(f"Orphan {orphan_id[:8]}... not found, skipping")
                    continue

                # Find most similar non-orphan memory
                similar = repo.search_similar_by_embedding(
                    embedding=repo._embedding_engine.embed(memory.content),
                    limit=3,
                    exclude_id=orphan_id,
                )

                for other_id, _, similarity, _, _ in similar:
                    if similarity < 0.5:  # Minimum threshold for rescue
                        continue

                    # Create a weak 'related' link
                    try:
                        service.link_memories(
                            source_id=orphan_id,
                            target_id=other_id,
                            relation_type=RelationType.RELATED,
                            reason=f"Auto-rescued orphan (similarity: {similarity:.2%})",
                        )
                        rescued += 1
                        logger.info(
                            f"Rescued orphan {orphan_id[:8]}... -> {other_id[:8]}..."
                        )
                        break  # Only link to top match
                    except Exception as e:
                        logger.debug(f"Could not rescue orphan: {e}")

            logger.info(f"Orphan rescue complete: {rescued} memories rescued")

        except Exception as e:
            logger.warning(f"Orphan rescue task error: {e}")

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._container is not None:
            try:
                self._container.close()
            except Exception as e:
                logger.warning(f"Error closing container: {e}")
            self._container = None

        logger.info("Dream worker shutdown complete")


def main() -> None:
    """Entry point for the dream worker process."""
    # Set log level from environment
    import os
    log_level = os.environ.get("EXOCORTEX_LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    worker = DreamWorker()
    worker.run()


if __name__ == "__main__":
    main()

