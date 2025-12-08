"""Statistics and analysis operations."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ...domain.models import MemoryStats

logger = logging.getLogger(__name__)


class StatsRepositoryMixin:
    """Mixin providing statistics and analysis operations.

    Requires BaseRepositoryMixin to be mixed in.
    """

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
            if row[0]:
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

    def get_orphan_memories(self, limit: int = 50) -> list[str]:
        """Get memories without any tags (orphans)."""
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:TAGGED_WITH]->(:Tag) }
            RETURN m.id
            LIMIT $limit
            """,
            parameters={"limit": limit},
        )

        orphans = []
        while result.has_next():
            orphans.append(result.get_next()[0])
        return orphans

    def get_unlinked_count(self) -> int:
        """Get count of memories with no RELATED_TO links."""
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:RELATED_TO]-() }
            RETURN count(m)
            """
        )
        return result.get_next()[0] if result.has_next() else 0

    def get_stale_memories(
        self,
        days_threshold: int = 90,
        limit: int = 50,
    ) -> list[str]:
        """Get memories not accessed in the specified number of days."""
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE m.last_accessed_at < $threshold
            RETURN m.id
            ORDER BY m.last_accessed_at ASC
            LIMIT $limit
            """,
            parameters={"threshold": threshold_date, "limit": limit},
        )

        stale = []
        while result.has_next():
            stale.append(result.get_next()[0])
        return stale
