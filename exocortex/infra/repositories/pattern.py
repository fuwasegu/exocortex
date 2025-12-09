"""Pattern operations for concept abstraction.

This module handles Pattern node creation and memory-to-pattern linking.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ...domain.models import MemoryWithContext, Pattern
from ..queries import MemoryQueryBuilder
from .base import BaseRepositoryMixin

logger = logging.getLogger(__name__)


class PatternMixin(BaseRepositoryMixin):
    """Mixin for pattern operations (Phase 2: Concept Abstraction)."""

    # =========================================================================
    # Create Pattern
    # =========================================================================

    def create_pattern(
        self,
        content: str,
        confidence: float = 0.5,
    ) -> tuple[str, str, list[float]]:
        """Create a new pattern in the database.

        Args:
            content: Pattern content (the generalized rule/insight).
            confidence: Initial confidence score (0.0-1.0).

        Returns:
            Tuple of (pattern_id, summary, embedding).
        """
        pattern_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        summary = self._generate_summary(content)
        embedding = self._embedding_engine.embed(content)

        self._execute_write(
            """
            CREATE (p:Pattern {
                id: $id,
                content: $content,
                summary: $summary,
                embedding: $embedding,
                confidence: $confidence,
                instance_count: $instance_count,
                created_at: $created_at,
                updated_at: $updated_at
            })
            """,
            parameters={
                "id": pattern_id,
                "content": content,
                "summary": summary,
                "embedding": embedding,
                "confidence": confidence,
                "instance_count": 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        self._release_write_lock()

        logger.info(f"Created pattern {pattern_id}")
        return pattern_id, summary, embedding

    # =========================================================================
    # Link Memory to Pattern
    # =========================================================================

    def link_memory_to_pattern(
        self,
        memory_id: str,
        pattern_id: str,
        confidence: float = 0.5,
    ) -> bool:
        """Link a memory as an instance of a pattern.

        Args:
            memory_id: The memory ID.
            pattern_id: The pattern ID.
            confidence: How strongly this memory exemplifies the pattern.

        Returns:
            True if successful.
        """
        now = datetime.now(timezone.utc)

        # Check if link already exists
        result = self._execute_read(
            """
            MATCH (m:Memory {id: $memory_id})-[r:INSTANCE_OF]->(p:Pattern {id: $pattern_id})
            RETURN count(r) as cnt
            """,
            parameters={"memory_id": memory_id, "pattern_id": pattern_id},
        )
        if result.has_next() and result.get_next()[0] > 0:
            logger.debug(f"Link already exists: {memory_id} -> {pattern_id}")
            return True

        # Create the link
        self._execute_write(
            """
            MATCH (m:Memory {id: $memory_id}), (p:Pattern {id: $pattern_id})
            CREATE (m)-[:INSTANCE_OF {confidence: $confidence, created_at: $created_at}]->(p)
            """,
            parameters={
                "memory_id": memory_id,
                "pattern_id": pattern_id,
                "confidence": confidence,
                "created_at": now,
            },
        )

        # Update pattern's instance count and confidence
        self._execute_write(
            """
            MATCH (p:Pattern {id: $pattern_id})
            SET p.instance_count = p.instance_count + 1,
                p.updated_at = $now,
                p.confidence = CASE
                    WHEN p.confidence < 0.9 THEN p.confidence + 0.05
                    ELSE p.confidence
                END
            """,
            parameters={"pattern_id": pattern_id, "now": now},
        )
        self._release_write_lock()

        logger.info(f"Linked memory {memory_id} to pattern {pattern_id}")
        return True

    # =========================================================================
    # Search Patterns
    # =========================================================================

    def search_similar_patterns(
        self,
        embedding: list[float],
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[tuple[str, str, float, float]]:
        """Search for similar patterns by embedding.

        Args:
            embedding: Query embedding vector.
            limit: Maximum results to return.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of (id, summary, similarity, confidence) tuples.
        """
        try:
            result = self._execute_read(
                """
                MATCH (p:Pattern)
                WHERE p.confidence >= $min_confidence
                RETURN p.id, p.summary, p.embedding, p.confidence
                """,
                parameters={"min_confidence": min_confidence},
            )

            # Compute similarity manually (Pattern table may not have vector index)
            patterns = []
            while result.has_next():
                row = result.get_next()
                if row[2]:  # has embedding
                    similarity = self.compute_similarity(embedding, row[2])
                    patterns.append((row[0], row[1], similarity, row[3]))

            # Sort by similarity and return top N
            patterns.sort(key=lambda x: x[2], reverse=True)
            return patterns[:limit]

        except Exception as e:
            logger.warning(f"Pattern search error: {e}")
            return []

    # =========================================================================
    # Get Pattern
    # =========================================================================

    def get_pattern_by_id(self, pattern_id: str) -> Pattern | None:
        """Get a pattern by ID.

        Args:
            pattern_id: The pattern ID.

        Returns:
            Pattern model or None if not found.
        """
        result = self._execute_read(
            """
            MATCH (p:Pattern {id: $id})
            RETURN p.id, p.content, p.summary, p.confidence,
                   p.instance_count, p.created_at, p.updated_at
            """,
            parameters={"id": pattern_id},
        )

        if not result.has_next():
            return None

        row = result.get_next()
        return Pattern(
            id=row[0],
            content=row[1],
            summary=row[2],
            confidence=row[3] if row[3] is not None else 0.5,
            instance_count=row[4] if row[4] is not None else 0,
            created_at=row[5],
            updated_at=row[6],
        )

    # =========================================================================
    # Get Memories by Tag/Frequency
    # =========================================================================

    def get_memories_by_tag(
        self,
        tag: str,
        limit: int = 50,
    ) -> list[MemoryWithContext]:
        """Get memories with a specific tag.

        Args:
            tag: Tag name to filter by.
            limit: Maximum results.

        Returns:
            List of memories with the tag.
        """
        result = self._execute_read(
            MemoryQueryBuilder.get_memories_by_tag(),
            parameters={"tag": tag.lower(), "limit": limit},
        )

        memories = []
        while result.has_next():
            row = result.get_next()
            memories.append(self._row_to_memory(row))

        return memories

    def get_frequently_accessed_memories(
        self,
        min_access_count: int = 3,
        limit: int = 100,
    ) -> list[MemoryWithContext]:
        """Get memories that are frequently accessed.

        Args:
            min_access_count: Minimum access count threshold.
            limit: Maximum results.

        Returns:
            List of frequently accessed memories.
        """
        result = self._execute_read(
            MemoryQueryBuilder.get_frequently_accessed(),
            parameters={"min_count": min_access_count, "limit": limit},
        )

        memories = []
        while result.has_next():
            row = result.get_next()
            memories.append(self._row_to_memory(row))

        return memories
