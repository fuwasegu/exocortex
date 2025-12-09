"""Statistics and health analysis operations.

This module handles memory statistics and knowledge health queries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ...domain.models import MemoryStats
from .base import BaseRepositoryMixin

logger = logging.getLogger(__name__)


class StatsMixin(BaseRepositoryMixin):
    """Mixin for statistics and health analysis operations."""

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories."""
        result = self._execute_read("MATCH (m:Memory) RETURN count(m)")
        total_memories = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("""
            MATCH (m:Memory)
            RETURN m.memory_type, count(m) as count
        """)
        memories_by_type: dict[str, int] = {}
        while result.has_next():
            row = result.get_next()
            memories_by_type[row[0]] = row[1]

        result = self._execute_read("MATCH (c:Context) RETURN count(c)")
        total_contexts = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("MATCH (t:Tag) RETURN count(t)")
        total_tags = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("""
            MATCH (m:Memory)-[:TAGGED_WITH]->(t:Tag)
            RETURN t.name, count(m) as count
            ORDER BY count DESC
            LIMIT 10
        """)
        top_tags: list[dict[str, Any]] = []
        while result.has_next():
            row = result.get_next()
            top_tags.append({"name": row[0], "count": row[1]})

        return MemoryStats(
            total_memories=total_memories,
            memories_by_type=memories_by_type,
            total_contexts=total_contexts,
            total_tags=total_tags,
            top_tags=top_tags,
        )

    # =========================================================================
    # Health Analysis
    # =========================================================================

    def get_orphan_memories(self, limit: int = 10) -> list[tuple[str, str]]:
        """Get memories without tags.

        Args:
            limit: Maximum number of memories to return.

        Returns:
            List of (id, summary) tuples for memories without tags.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:TAGGED_WITH]->(:Tag) }
            RETURN m.id, m.summary
            LIMIT $limit
            """,
            parameters={"limit": limit},
        )
        memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            memories.append((row[0], row[1]))
        return memories

    def get_unlinked_count(self) -> int:
        """Get count of memories without any RELATED_TO links."""
        result = self._execute_read("""
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:RELATED_TO]->(:Memory) }
              AND NOT EXISTS { MATCH (:Memory)-[:RELATED_TO]->(m) }
            RETURN count(m)
        """)
        return result.get_next()[0] if result.has_next() else 0

    def get_stale_memories(
        self, threshold: datetime, limit: int = 10
    ) -> list[tuple[str, str]]:
        """Get memories not updated since threshold.

        Args:
            threshold: Datetime threshold. Memories not updated since this time are stale.
            limit: Maximum number of memories to return.

        Returns:
            List of (id, summary) tuples for stale memories.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE m.updated_at < $threshold
            RETURN m.id, m.summary
            LIMIT $limit
            """,
            parameters={"threshold": threshold, "limit": limit},
        )
        memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            memories.append((row[0], row[1]))
        return memories
