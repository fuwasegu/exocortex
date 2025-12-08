"""Search and retrieval operations."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from ...domain.models import MemoryType, MemoryWithContext
from ..queries import MemoryQueryBuilder

logger = logging.getLogger(__name__)


class SearchRepositoryMixin:
    """Mixin providing search and retrieval operations.

    Requires BaseRepositoryMixin to be mixed in.
    """

    def search_similar_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 10,
        threshold: float = 0.0,
    ) -> list[tuple[MemoryWithContext, float]]:
        """Search memories by embedding similarity.

        Returns list of (memory, similarity_score) tuples.
        """
        # Get all memories with embeddings
        result = self._execute_read(
            """
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at,
                   m.last_accessed_at, m.access_count, m.decay_rate,
                   m.frustration_score, m.time_cost_hours,
                   c.name as context, collect(t.name) as tags, m.embedding
            """
        )

        memories_with_scores = []
        while result.has_next():
            row = result.get_next()
            embedding = row[13]  # embedding is the last column
            if embedding:
                similarity = self.compute_similarity(query_embedding, embedding)
                if similarity >= threshold:
                    memory = self._row_to_memory(row)
                    memories_with_scores.append((memory, similarity))

        # Sort by similarity descending
        memories_with_scores.sort(key=lambda x: x[1], reverse=True)

        return memories_with_scores[:limit]

    def _search_similar_fallback(
        self,
        query_embedding: list[float],
        limit: int = 10,
        context_filter: str | None = None,
    ) -> list[tuple[MemoryWithContext, float]]:
        """Fallback similarity search without HNSW index."""
        # Get all memories with optional context filter
        if context_filter:
            result = self._execute_read(
                """
                MATCH (m:Memory)-[:ORIGINATED_IN]->(c:Context {name: $context})
                OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
                RETURN m.id, m.content, m.summary, m.memory_type,
                       m.created_at, m.updated_at,
                       m.last_accessed_at, m.access_count, m.decay_rate,
                       m.frustration_score, m.time_cost_hours,
                       c.name, collect(t.name) as tags, m.embedding
                """,
                parameters={"context": context_filter},
            )
        else:
            result = self._execute_read(
                """
                MATCH (m:Memory)
                OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
                OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
                RETURN m.id, m.content, m.summary, m.memory_type,
                       m.created_at, m.updated_at,
                       m.last_accessed_at, m.access_count, m.decay_rate,
                       m.frustration_score, m.time_cost_hours,
                       c.name, collect(t.name) as tags, m.embedding
                """
            )

        return self._compute_similarities(result, query_embedding, limit)

    def _compute_similarities(
        self,
        result,
        query_embedding: list[float],
        limit: int,
    ) -> list[tuple[MemoryWithContext, float]]:
        """Compute similarities for query results."""
        memories_with_scores = []
        while result.has_next():
            row = result.get_next()
            embedding = row[13]
            if embedding:
                similarity = self.compute_similarity(query_embedding, embedding)
                memory = self._row_to_memory(row)
                memories_with_scores.append((memory, similarity))

        memories_with_scores.sort(key=lambda x: x[1], reverse=True)
        return memories_with_scores[:limit]

    def search_by_similarity(
        self,
        query: str,
        limit: int = 10,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
    ) -> list[MemoryWithContext]:
        """Search memories by semantic similarity with hybrid scoring.

        Combines vector similarity with recency and frequency for ranking.
        """
        query_embedding = self._embedding_engine.embed(query)

        # Use fallback search (compute similarity for all memories)
        results = self._search_similar_fallback(
            query_embedding, limit=100, context_filter=context_filter
        )

        # Apply tag filter if specified
        if tag_filter:
            tag_set = {t.lower() for t in tag_filter}
            results = [(m, s) for m, s in results if tag_set.intersection(set(m.tags))]

        # Apply hybrid scoring
        scored_results = self._apply_hybrid_scoring(results)

        # Sort by hybrid score and return top results
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [m for m, _ in scored_results[:limit]]

    def _apply_hybrid_scoring(
        self,
        results: list[tuple[MemoryWithContext, float]],
        w_similarity: float = 0.5,
        w_recency: float = 0.25,
        w_frequency: float = 0.15,
        w_frustration: float = 0.1,
    ) -> list[tuple[MemoryWithContext, float]]:
        """Apply hybrid scoring combining similarity, recency, frequency, and frustration.

        Formula:
            hybrid_score = w_s * S_similarity + w_r * S_recency + w_f * S_frequency + w_fr * S_frustration

        Where:
            - S_similarity: Vector similarity (already computed)
            - S_recency: Time decay based on last_accessed_at
            - S_frequency: Log-normalized access count
            - S_frustration: Frustration score (0.0-1.0)
        """
        if not results:
            return []

        now = datetime.now(timezone.utc)

        # Normalize access counts for frequency scoring
        max_access = max((m.access_count for m, _ in results), default=1)
        if max_access == 0:
            max_access = 1

        scored_results = []
        for memory, similarity in results:
            # S_recency: exponential decay based on days since last access
            if memory.last_accessed_at:
                last_accessed = memory.last_accessed_at
                if last_accessed.tzinfo is None:
                    last_accessed = last_accessed.replace(tzinfo=timezone.utc)
                days_since_access = (now - last_accessed).total_seconds() / 86400
                # Decay half-life of 30 days
                s_recency = math.exp(-0.693 * days_since_access / 30)
            else:
                s_recency = 0.5  # Default for memories without access history

            # S_frequency: log-normalized access count
            s_frequency = math.log1p(memory.access_count) / math.log1p(max_access)

            # S_frustration: directly use frustration_score (already 0.0-1.0)
            s_frustration = memory.frustration_score

            # Compute hybrid score
            hybrid_score = (
                w_similarity * similarity
                + w_recency * s_recency
                + w_frequency * s_frequency
                + w_frustration * s_frustration
            )

            scored_results.append((memory, hybrid_score))

        return scored_results

    def explore_related(
        self,
        memory_id: str,
        include_tag_siblings: bool = True,
        include_context_siblings: bool = True,
        max_per_category: int = 5,
    ) -> dict[str, list[MemoryWithContext]]:
        """Explore memories related to a given memory."""
        result_dict: dict[str, list[MemoryWithContext]] = {
            "linked": [],
            "by_tag": [],
            "by_context": [],
        }

        # Get directly linked memories
        result = self._execute_read(
            MemoryQueryBuilder.explore_linked(),
            parameters={"id": memory_id, "limit": max_per_category},
        )

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[12] if t]
            memory = MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                last_accessed_at=row[6],
                access_count=row[7] or 1,
                decay_rate=row[8] or 1.0,
                frustration_score=row[9] or 0.0,
                time_cost_hours=row[10],
                context=row[11],
                tags=tags,
            )
            result_dict["linked"].append(memory)

        # Get tag siblings
        if include_tag_siblings:
            result = self._execute_read(
                MemoryQueryBuilder.explore_tag_siblings(),
                parameters={"id": memory_id, "limit": max_per_category},
            )

            seen_ids = {m.id for m in result_dict["linked"]}
            while result.has_next():
                row = result.get_next()
                if row[0] in seen_ids:
                    continue
                result_dict["by_tag"].append(self._row_to_memory(row))
                seen_ids.add(row[0])

        # Get context siblings
        if include_context_siblings:
            result = self._execute_read(
                MemoryQueryBuilder.explore_context_siblings(),
                parameters={"id": memory_id, "limit": max_per_category},
            )

            seen_ids = {m.id for m in result_dict["linked"]}
            seen_ids.update(m.id for m in result_dict["by_tag"])
            while result.has_next():
                row = result.get_next()
                if row[0] in seen_ids:
                    continue
                result_dict["by_context"].append(self._row_to_memory(row))

        return result_dict

    def get_memories_by_tag(
        self,
        tag: str,
        limit: int = 20,
    ) -> list[MemoryWithContext]:
        """Get memories with a specific tag, ordered by access count."""
        result = self._execute_read(
            MemoryQueryBuilder.get_memories_by_tag(),
            parameters={"tag": tag.lower(), "limit": limit},
        )

        memories = []
        while result.has_next():
            memories.append(self._row_to_memory(result.get_next()))
        return memories

    def get_frequently_accessed_memories(
        self,
        min_access_count: int = 3,
        limit: int = 20,
    ) -> list[MemoryWithContext]:
        """Get frequently accessed memories."""
        result = self._execute_read(
            MemoryQueryBuilder.get_frequently_accessed(),
            parameters={"min_count": min_access_count, "limit": limit},
        )

        memories = []
        while result.has_next():
            memories.append(self._row_to_memory(result.get_next()))
        return memories
