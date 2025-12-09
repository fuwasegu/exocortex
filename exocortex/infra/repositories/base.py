"""Base repository mixin with common functionality.

This module provides the foundation for all repository operations including:
- Database connection management
- Query execution (read/write)
- Row-to-model conversion
- Tag management
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ...domain.models import (
    MemoryLink,
    MemoryType,
    MemoryWithContext,
)
from ..database import DatabaseConnection, SmartDatabaseManager
from ..embeddings import EmbeddingEngine

if TYPE_CHECKING:
    import kuzu

logger = logging.getLogger(__name__)


class BaseRepositoryMixin:
    """Base mixin providing common repository functionality.

    All other repository mixins should inherit from this class to access
    shared methods like _execute_read, _execute_write, and _row_to_memory.
    """

    # These will be set by __init__ in the concrete class
    _db_manager: SmartDatabaseManager | DatabaseConnection
    _embedding_engine: EmbeddingEngine
    _max_summary_length: int
    _use_smart_manager: bool

    def _init_base(
        self,
        db_manager: SmartDatabaseManager | DatabaseConnection,
        embedding_engine: EmbeddingEngine,
        max_summary_length: int = 200,
    ) -> None:
        """Initialize base repository attributes.

        Args:
            db_manager: Smart database manager or legacy database connection.
            embedding_engine: Embedding engine for vector operations.
            max_summary_length: Maximum length for summaries.
        """
        self._db_manager = db_manager
        self._embedding_engine = embedding_engine
        self._max_summary_length = max_summary_length
        self._use_smart_manager = isinstance(db_manager, SmartDatabaseManager)

    # =========================================================================
    # Connection Management
    # =========================================================================

    def _get_read_connection(self) -> DatabaseConnection:
        """Get a read-only database connection."""
        if self._use_smart_manager:
            return self._db_manager.read_connection  # type: ignore
        return self._db_manager  # type: ignore

    def _execute_read(
        self, query: str, parameters: dict | None = None
    ) -> kuzu.QueryResult:
        """Execute a read query using read-only connection."""
        conn = self._get_read_connection()
        if parameters:
            return conn.execute(query, parameters=parameters)
        return conn.execute(query)

    def _execute_write(
        self, query: str, parameters: dict | None = None
    ) -> kuzu.QueryResult:
        """Execute a write query using read-write connection.

        For smart manager, this uses the write context with retry logic.
        Note: Call _release_write_lock() after completing all writes in a batch.
        """
        if self._use_smart_manager:
            write_conn = self._db_manager.get_write_connection()  # type: ignore
            if parameters:
                return write_conn.execute(query, parameters=parameters)
            return write_conn.execute(query)
        else:
            # Legacy mode - use same connection
            if parameters:
                return self._db_manager.execute(query, parameters=parameters)  # type: ignore
            return self._db_manager.execute(query)  # type: ignore

    def _release_write_lock(self) -> None:
        """Release the write lock after completing write operations."""
        if self._use_smart_manager:
            self._db_manager.release_write_lock()  # type: ignore

    # =========================================================================
    # Utilities
    # =========================================================================

    def compute_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Compute similarity between two embeddings."""
        return self._embedding_engine.compute_similarity(embedding1, embedding2)

    def _generate_summary(self, content: str) -> str:
        """Generate a summary from content."""
        content = content.strip()
        if len(content) <= self._max_summary_length:
            return content

        truncated = content[: self._max_summary_length]
        last_space = truncated.rfind(" ")
        if last_space > self._max_summary_length * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    # =========================================================================
    # Tag Management
    # =========================================================================

    def _create_tag_relationships(
        self, memory_id: str, tags: list[str], timestamp: datetime
    ) -> None:
        """Create tag nodes and relationships for a memory."""
        for tag in tags:
            tag_normalized = tag.strip().lower()
            if not tag_normalized:
                continue

            self._execute_write(
                """
                MERGE (t:Tag {name: $name})
                ON CREATE SET t.created_at = $created_at
                """,
                parameters={"name": tag_normalized, "created_at": timestamp},
            )

            self._execute_write(
                """
                MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"memory_id": memory_id, "tag_name": tag_normalized},
            )

    # =========================================================================
    # Row Mapping
    # =========================================================================

    def _row_to_memory(
        self,
        row: tuple,
        include_content: bool = True,
        similarity: float | None = None,
        related_memories: list[MemoryLink] | None = None,
    ) -> MemoryWithContext:
        """Convert a database row to MemoryWithContext.

        Row format with content (include_content=True):
            (id, content, summary, memory_type, created_at, updated_at,
             last_accessed_at, access_count, decay_rate,
             frustration_score, time_cost_hours, context, tags)

        Row format without content (include_content=False):
            (id, summary, memory_type, created_at, updated_at,
             last_accessed_at, access_count, decay_rate,
             frustration_score, time_cost_hours, context, tags)
        """
        if include_content:
            tags = [t for t in row[12] if t] if row[12] else []
            return MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                last_accessed_at=row[6],
                access_count=row[7] if row[7] is not None else 1,
                decay_rate=row[8] if row[8] is not None else 0.1,
                frustration_score=row[9] if row[9] is not None else 0.0,
                time_cost_hours=row[10],
                context=row[11],
                tags=tags,
                similarity=similarity,
                related_memories=related_memories or [],
            )
        else:
            tags = [t for t in row[11] if t] if row[11] else []
            return MemoryWithContext(
                id=row[0],
                content="",
                summary=row[1],
                memory_type=MemoryType(row[2]),
                created_at=row[3],
                updated_at=row[4],
                last_accessed_at=row[5],
                access_count=row[6] if row[6] is not None else 1,
                decay_rate=row[7] if row[7] is not None else 0.1,
                frustration_score=row[8] if row[8] is not None else 0.0,
                time_cost_hours=row[9],
                context=row[10],
                tags=tags,
                similarity=similarity,
                related_memories=related_memories or [],
            )
