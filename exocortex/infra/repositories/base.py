"""Base repository with common database operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..database import DatabaseConnection, SmartDatabaseManager
from ..embeddings import EmbeddingEngine

if TYPE_CHECKING:
    import kuzu

logger = logging.getLogger(__name__)


class BaseRepositoryMixin:
    """Base mixin providing common database operations.

    This mixin provides:
    - Database connection management
    - Read/Write execution helpers
    - Embedding computation
    - Summary generation
    """

    _db_manager: DatabaseConnection | SmartDatabaseManager
    _embedding_engine: EmbeddingEngine
    _max_summary_length: int
    _use_smart_manager: bool

    def __init__(
        self,
        db_manager: DatabaseConnection | SmartDatabaseManager,
        embedding_engine: EmbeddingEngine,
        max_summary_length: int = 200,
    ) -> None:
        """Initialize repository with database and embedding dependencies."""
        self._db_manager = db_manager
        self._embedding_engine = embedding_engine
        self._max_summary_length = max_summary_length

        # Check if we're using SmartDatabaseManager (SSE mode)
        self._use_smart_manager = isinstance(db_manager, SmartDatabaseManager)

    def _get_read_connection(self) -> DatabaseConnection:
        """Get a connection for read operations."""
        if self._use_smart_manager:
            return self._db_manager.read_connection  # type: ignore
        return self._db_manager  # type: ignore

    def _execute_read(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> kuzu.QueryResult:
        """Execute a read query using read-only connection."""
        conn = self._get_read_connection()
        if parameters:
            return conn.execute(query, parameters=parameters)
        return conn.execute(query)

    def _execute_write(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> kuzu.QueryResult:
        """Execute a write query with proper locking.

        Note: For SmartDatabaseManager, caller should call _release_write_lock()
        after completing all writes in a batch.
        """
        if self._use_smart_manager:
            # SSE mode: use SmartDatabaseManager's write connection
            write_conn = self._db_manager.get_write_connection()
            if parameters:
                return write_conn.execute(query, parameters=parameters)
            return write_conn.execute(query)
        else:
            # stdio mode: direct execution via DatabaseConnection.execute
            if parameters:
                return self._db_manager.execute(query, parameters=parameters)
            return self._db_manager.execute(query)

    def _release_write_lock(self) -> None:
        """Release write lock if using SmartDatabaseManager."""
        if self._use_smart_manager:
            try:
                self._db_manager.release_write_lock()
            except RuntimeError:
                # Lock not held, ignore
                pass

    def compute_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _generate_summary(self, content: str) -> str:
        """Generate a summary from content.

        For now, simply truncate. In the future, could use LLM.
        """
        content = content.strip()
        if len(content) <= self._max_summary_length:
            return content
        # Find a good break point
        truncated = content[: self._max_summary_length]
        last_period = truncated.rfind(".")
        if last_period > self._max_summary_length // 2:
            return truncated[: last_period + 1]
        return truncated + "..."
