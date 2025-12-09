"""Pattern Consolidator - Extracts patterns from memory clusters.

This module implements the "Abstraction" mechanism (Phase 2) that:
1. Clusters memories by tag or high similarity
2. Identifies common patterns/rules across the cluster
3. Creates Pattern nodes and links instances
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..models import MemoryWithContext

if TYPE_CHECKING:
    from ...infra.repositories import MemoryRepository

logger = logging.getLogger(__name__)


class PatternConsolidator:
    """Extracts and consolidates patterns from memory clusters."""

    def __init__(
        self,
        repository: MemoryRepository,
    ) -> None:
        """Initialize the consolidator.

        Args:
            repository: Memory repository for data access.
        """
        self._repo = repository

    def consolidate(
        self,
        tag_filter: str | None = None,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
    ) -> dict:
        """Extract patterns from clusters of similar memories.

        Args:
            tag_filter: Optional tag to focus pattern extraction.
            min_cluster_size: Minimum memories to form a pattern.
            similarity_threshold: Minimum similarity for clustering.

        Returns:
            Summary of patterns found/created.
        """
        result = {
            "patterns_found": 0,
            "patterns_created": 0,
            "memories_linked": 0,
            "details": [],
        }

        # Get candidate memories
        if tag_filter:
            candidates = self._repo.get_memories_by_tag(tag_filter, limit=100)
            logger.info(
                f"Consolidating patterns for tag '{tag_filter}': {len(candidates)} memories"
            )
        else:
            # Focus on frequently accessed memories
            candidates = self._repo.get_frequently_accessed_memories(
                min_access_count=3, limit=100
            )
            logger.info(
                f"Consolidating patterns for frequently accessed memories: {len(candidates)}"
            )

        if len(candidates) < min_cluster_size:
            logger.info("Not enough memories to extract patterns")
            return result

        # Find clusters of similar memories
        clusters = self._find_clusters(
            candidates, similarity_threshold, min_cluster_size
        )

        for cluster in clusters:
            # Check if a similar pattern already exists
            cluster_content = " ".join([m.content for m in cluster[:3]])  # Sample
            embedding = self._repo._embedding_engine.embed(cluster_content)

            similar_patterns = self._repo.search_similar_patterns(
                embedding=embedding,
                limit=3,
                min_confidence=0.3,
            )

            if similar_patterns and similar_patterns[0][2] >= 0.8:
                # Link memories to existing pattern
                pattern_id = similar_patterns[0][0]
                for memory in cluster:
                    self._repo.link_memory_to_pattern(
                        memory_id=memory.id,
                        pattern_id=pattern_id,
                        confidence=similar_patterns[0][2],
                    )
                    result["memories_linked"] += 1
                result["patterns_found"] += 1
                logger.info(
                    f"Linked {len(cluster)} memories to existing pattern {pattern_id[:8]}..."
                )
            else:
                # Create new pattern from cluster
                pattern_content = self._synthesize_content(cluster)
                if pattern_content:
                    pattern_id, summary, _ = self._repo.create_pattern(
                        content=pattern_content,
                        confidence=0.5,
                    )

                    # Link all cluster memories to the new pattern
                    for memory in cluster:
                        self._repo.link_memory_to_pattern(
                            memory_id=memory.id,
                            pattern_id=pattern_id,
                            confidence=0.6,
                        )
                        result["memories_linked"] += 1

                    result["patterns_created"] += 1
                    result["details"].append(
                        {
                            "pattern_id": pattern_id,
                            "summary": summary,
                            "instance_count": len(cluster),
                        }
                    )
                    logger.info(
                        f"Created new pattern {pattern_id[:8]}... from {len(cluster)} memories"
                    )

        return result

    def _find_clusters(
        self,
        memories: list[MemoryWithContext],
        threshold: float,
        min_size: int,
    ) -> list[list[MemoryWithContext]]:
        """Find clusters of similar memories.

        Uses a simple greedy clustering approach.

        Args:
            memories: List of memories to cluster.
            threshold: Similarity threshold for clustering.
            min_size: Minimum cluster size.

        Returns:
            List of memory clusters.
        """
        if not memories:
            return []

        clusters: list[list[MemoryWithContext]] = []
        used: set[str] = set()

        for memory in memories:
            if memory.id in used:
                continue

            # Start a new cluster with this memory
            cluster = [memory]
            used.add(memory.id)

            # Find similar memories
            embedding = self._repo._embedding_engine.embed(memory.content)
            for other in memories:
                if other.id in used:
                    continue

                other_embedding = self._repo._embedding_engine.embed(other.content)
                similarity = self._repo.compute_similarity(embedding, other_embedding)

                if similarity >= threshold:
                    cluster.append(other)
                    used.add(other.id)

            if len(cluster) >= min_size:
                clusters.append(cluster)

        return clusters

    def _synthesize_content(
        self,
        cluster: list[MemoryWithContext],
    ) -> str | None:
        """Synthesize a pattern description from a cluster of memories.

        This is a simple heuristic approach. A more sophisticated version
        could use an LLM to generate the pattern.

        Args:
            cluster: List of memories in the cluster.

        Returns:
            Synthesized pattern content or None.
        """
        if not cluster:
            return None

        # Find common tags
        tag_counts: dict[str, int] = {}
        for memory in cluster:
            for tag in memory.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        common_tags = [
            tag
            for tag, count in tag_counts.items()
            if count >= len(cluster) * 0.5  # At least 50% of memories have this tag
        ]

        # Find common memory types
        type_counts: dict[str, int] = {}
        for memory in cluster:
            mt = memory.memory_type.value
            type_counts[mt] = type_counts.get(mt, 0) + 1

        dominant_type = (
            max(type_counts.items(), key=lambda x: x[1])[0]
            if type_counts
            else "insight"
        )

        # Generate pattern content
        summaries = [m.summary for m in cluster[:5]]  # Use first 5 summaries
        pattern_parts = [
            f"**Pattern extracted from {len(cluster)} memories**",
            "",
            f"- Dominant type: {dominant_type}",
            f"- Common tags: {', '.join(common_tags) if common_tags else 'none'}",
            "",
            "**Representative examples:**",
        ]
        for i, summary in enumerate(summaries, 1):
            pattern_parts.append(f"{i}. {summary}")

        return "\n".join(pattern_parts)
