"""Search operations with hybrid scoring.

This module handles vector similarity search and hybrid scoring logic.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from ...domain.models import MemoryType, MemoryWithContext
from ..queries import MemoryQueryBuilder
from .base import BaseRepositoryMixin

logger = logging.getLogger(__name__)


class SearchMixin(BaseRepositoryMixin):
    """Mixin for search operations with hybrid scoring."""

    # =========================================================================
    # Vector Search
    # =========================================================================

    def search_similar_by_embedding(
        self,
        embedding: list[float],
        limit: int = 10,
        exclude_id: str | None = None,
    ) -> list[tuple[str, str, float, str, str | None]]:
        """Search similar memories using KùzuDB native vector search.

        Uses the vector index for efficient similarity search.

        Args:
            embedding: Query embedding vector.
            limit: Maximum results to return.
            exclude_id: Optional memory ID to exclude from results.

        Returns:
            List of (id, summary, similarity, memory_type, context) tuples,
            sorted by similarity descending.
        """
        fetch_limit = limit + 5 if exclude_id else limit

        try:
            result = self._execute_read(
                """
                CALL QUERY_VECTOR_INDEX('Memory', 'memory_embedding_idx', $embedding, $k)
                YIELD node, distance
                MATCH (node)
                OPTIONAL MATCH (node)-[:ORIGINATED_IN]->(c:Context)
                RETURN node.id, node.summary, 1 - distance as similarity,
                       node.memory_type, c.name as context
                ORDER BY similarity DESC
                """,
                parameters={"embedding": embedding, "k": fetch_limit},
            )
        except Exception as e:
            logger.warning(f"Vector index search failed, using fallback: {e}")
            return self._search_similar_fallback(embedding, limit, exclude_id)

        memories = []
        while result.has_next():
            row = result.get_next()
            if exclude_id and row[0] == exclude_id:
                continue
            memories.append((row[0], row[1], row[2], row[3], row[4]))
            if len(memories) >= limit:
                break

        return memories

    def _search_similar_fallback(
        self,
        embedding: list[float],
        limit: int,
        exclude_id: str | None,
    ) -> list[tuple[str, str, float, str, str | None]]:
        """Fallback similarity search using Python-side computation."""
        result = self._execute_read("""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            RETURN m.id, m.summary, m.embedding, m.memory_type, c.name as context
        """)

        memories_with_scores: list[tuple[str, str, float, str, str | None]] = []

        while result.has_next():
            row = result.get_next()
            memory_id = row[0]
            if exclude_id and memory_id == exclude_id:
                continue

            similarity = self._embedding_engine.compute_similarity(embedding, row[2])
            memories_with_scores.append((memory_id, row[1], similarity, row[3], row[4]))

        memories_with_scores.sort(key=lambda x: x[2], reverse=True)
        return memories_with_scores[:limit]

    # =========================================================================
    # High-Level Search
    # =========================================================================

    def search_by_similarity(
        self,
        query: str,
        limit: int = 5,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
        use_hybrid_scoring: bool = True,
    ) -> tuple[list[MemoryWithContext], int]:
        """Search memories by semantic similarity with hybrid scoring.

        Args:
            query: Search query.
            limit: Maximum results.
            context_filter: Filter by context.
            tag_filter: Filter by tags.
            type_filter: Filter by type.
            use_hybrid_scoring: If True, apply hybrid scoring algorithm.

        Returns:
            Tuple of (memories, total_found).
        """
        query_embedding = self._embedding_engine.embed(query)

        # Fetch more candidates to account for filtering and reranking
        fetch_multiplier = 5 if use_hybrid_scoring else 3
        if context_filter or tag_filter or type_filter:
            fetch_multiplier += 2
        candidates = self.search_similar_by_embedding(
            embedding=query_embedding,
            limit=limit * fetch_multiplier + 20,
        )

        memories: list[MemoryWithContext] = []

        for memory_id, _summary, similarity, memory_type, context in candidates:
            # Apply filters
            if context_filter and context != context_filter:
                continue
            if type_filter and memory_type != type_filter.value:
                continue

            # Get full memory with tags for tag filtering
            full_memory = self.get_by_id(memory_id)  # type: ignore
            if full_memory is None:
                continue

            if tag_filter:
                tag_set = set(full_memory.tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            full_memory.similarity = similarity
            memories.append(full_memory)

        # Apply hybrid scoring if enabled
        if use_hybrid_scoring and memories:
            memories = self._apply_hybrid_scoring(memories)

        return memories[:limit], len(memories[:limit])

    # =========================================================================
    # Hybrid Scoring
    # =========================================================================

    def _apply_hybrid_scoring(
        self,
        memories: list[MemoryWithContext],
        w_vec: float = 0.5,
        w_recency: float = 0.2,
        w_freq: float = 0.15,
        w_frustration: float = 0.15,
        decay_lambda: float = 0.01,
    ) -> list[MemoryWithContext]:
        """Apply hybrid scoring algorithm to rerank memories.

        Combines four signals (Somatic Marker Hypothesis integration):
        - S_vec: Vector similarity score (0-1)
        - S_recency: Recency score based on last_accessed_at (exponential decay)
        - S_freq: Frequency score based on access_count (logarithmic scale)
        - S_frustration: Frustration score - painful memories are prioritized

        Formula: Score = (S_vec * w_vec) + (S_recency * w_recency) +
                        (S_freq * w_freq) + (S_frustration * w_frustration)
        """
        now = datetime.now(timezone.utc)
        scored_memories: list[tuple[float, MemoryWithContext]] = []

        # Find max access_count for normalization
        max_access = max((m.access_count for m in memories), default=1)
        max_log_access = math.log(1 + max_access)

        for memory in memories:
            # S_vec: Vector similarity (already 0-1)
            s_vec = memory.similarity if memory.similarity is not None else 0.0

            # S_recency: Exponential decay based on time since last access
            reference_time = memory.last_accessed_at or memory.created_at
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=timezone.utc)
            delta_days = (now - reference_time).total_seconds() / 86400.0
            s_recency = math.exp(-decay_lambda * delta_days)

            # S_freq: Logarithmic scale for access count (normalized)
            access_count = memory.access_count if memory.access_count else 1
            s_freq = (
                math.log(1 + access_count) / max_log_access if max_log_access > 0 else 0
            )

            # S_frustration: Frustration score (Somatic Marker Hypothesis)
            s_frustration = (
                memory.frustration_score if memory.frustration_score else 0.0
            )

            # Combined hybrid score
            hybrid_score = (
                (s_vec * w_vec)
                + (s_recency * w_recency)
                + (s_freq * w_freq)
                + (s_frustration * w_frustration)
            )

            scored_memories.append((hybrid_score, memory))

            logger.debug(
                f"Memory {memory.id[:8]}... hybrid={hybrid_score:.3f} "
                f"(vec={s_vec:.3f}, recency={s_recency:.3f}, "
                f"freq={s_freq:.3f}, frustration={s_frustration:.3f})"
            )

        # Sort by hybrid score (descending)
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Update similarity field with hybrid score for transparency
        result = []
        for hybrid_score, memory in scored_memories:
            memory.similarity = hybrid_score
            result.append(memory)

        return result

    # =========================================================================
    # List Operations
    # =========================================================================

    def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
    ) -> tuple[list[MemoryWithContext], int, bool]:
        """List memories with pagination."""
        where_clauses = []
        params: dict[str, Any] = {}

        if context_filter:
            where_clauses.append("c.name = $context_filter")
            params["context_filter"] = context_filter

        if type_filter:
            where_clauses.append("m.memory_type = $type_filter")
            params["type_filter"] = type_filter.value

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # Get total count
        count_query = f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            WHERE {where_clause}
            RETURN count(DISTINCT m.id) as total
        """
        count_result = self._execute_read(count_query, parameters=params)
        total_count = count_result.get_next()[0] if count_result.has_next() else 0

        # Get memories
        query = MemoryQueryBuilder.list_memories(where_clause)
        params["offset"] = offset
        params["limit"] = limit

        result = self._execute_read(query, parameters=params)
        memories: list[MemoryWithContext] = []

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[12] if t] if row[12] else []

            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            memories.append(self._row_to_memory(row))

        has_more = offset + len(memories) < total_count
        return memories, total_count, has_more
