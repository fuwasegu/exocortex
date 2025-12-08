"""Domain services - Core business logic for Exocortex."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .exceptions import ValidationError
from .models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    KnowledgeInsight,
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
    StoreMemoryResult,
    SuggestedLink,
)

if TYPE_CHECKING:
    from ..infra.repositories import MemoryRepository

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for memory-related business logic."""

    def __init__(
        self,
        repository: MemoryRepository,
        link_threshold: float = 0.65,
        duplicate_threshold: float = 0.90,
        contradiction_threshold: float = 0.70,
        max_tags: int = 20,
        stale_days: int = 90,
    ) -> None:
        """Initialize the service.

        Args:
            repository: Memory repository for data access.
            link_threshold: Similarity threshold for suggesting links.
            duplicate_threshold: Similarity threshold for duplicate detection.
            contradiction_threshold: Similarity threshold for contradiction check.
            max_tags: Maximum allowed tags per memory.
            stale_days: Days after which a memory is considered stale.
        """
        self._repo = repository
        self._link_threshold = link_threshold
        self._duplicate_threshold = duplicate_threshold
        self._contradiction_threshold = contradiction_threshold
        self._max_tags = max_tags
        self._stale_days = stale_days

    def _validate_input(self, content: str, context_name: str, tags: list[str]) -> None:
        """Validate input for storing a memory."""
        if not content or not content.strip():
            raise ValidationError("Content cannot be empty")
        if not context_name or not context_name.strip():
            raise ValidationError("Context name cannot be empty")
        if len(tags) > self._max_tags:
            raise ValidationError(
                f"Too many tags (max {self._max_tags}, got {len(tags)})"
            )

    def store_memory(
        self,
        content: str,
        context_name: str,
        tags: list[str],
        memory_type: MemoryType = MemoryType.INSIGHT,
        auto_analyze: bool = True,
        is_painful: bool | None = None,
        time_cost_hours: float | None = None,
    ) -> StoreMemoryResult:
        """Store a new memory with automatic knowledge analysis.

        Args:
            content: Memory content.
            context_name: Context/project name.
            tags: List of tags.
            memory_type: Type of memory.
            auto_analyze: Whether to analyze for similar memories.
            is_painful: Explicit flag for frustrating memories.
            time_cost_hours: Explicit time spent on the problem.

        Returns:
            StoreMemoryResult with suggestions and insights.

        Raises:
            ValidationError: If input validation fails.
        """
        self._validate_input(content, context_name, tags)

        # Calculate frustration index using Amygdala module
        from exocortex.brain.amygdala import FrustrationIndexer

        indexer = FrustrationIndexer()
        frustration_index = indexer.index(
            content=content,
            is_painful=is_painful,
            time_cost_hours=time_cost_hours,
        )

        memory_id, summary, embedding = self._repo.create_memory(
            content=content,
            context_name=context_name,
            tags=tags,
            memory_type=memory_type,
            frustration_score=frustration_index.frustration_score,
            time_cost_hours=frustration_index.time_cost_hours,
        )

        suggested_links: list[SuggestedLink] = []
        insights: list[KnowledgeInsight] = []

        if auto_analyze:
            suggested_links, insights = self._analyze_new_memory(
                memory_id, content, embedding, memory_type
            )

        return StoreMemoryResult(
            success=True,
            memory_id=memory_id,
            summary=summary,
            suggested_links=suggested_links,
            insights=insights,
        )

    def _analyze_new_memory(
        self,
        new_memory_id: str,
        content: str,
        embedding: list[float],
        memory_type: MemoryType,
    ) -> tuple[list[SuggestedLink], list[KnowledgeInsight]]:
        """Analyze a new memory for potential links and insights.

        Uses KùzuDB's native vector search for efficient similarity lookup.
        """
        suggested_links: list[SuggestedLink] = []
        insights: list[KnowledgeInsight] = []

        contradiction_keywords = [
            "but",
            "however",
            "instead",
            "wrong",
            "incorrect",
            "not",
            "don't",
            "shouldn't",
            "actually",
            "contrary",
        ]

        # Use native vector search to find similar memories efficiently
        # Fetch top 10 similar memories (excluding the new one)
        similar_memories = self._repo.search_similar_by_embedding(
            embedding=embedding,
            limit=10,
            exclude_id=new_memory_id,
        )

        # Filter by link threshold
        similar_memories = [
            (mid, summary, sim, mtype, ctx)
            for mid, summary, sim, mtype, ctx in similar_memories
            if sim > self._link_threshold
        ]

        for (
            other_id,
            other_summary,
            similarity,
            other_type,
            other_context,
        ) in similar_memories[:5]:
            if similarity > self._duplicate_threshold:
                insights.append(
                    KnowledgeInsight(
                        insight_type="potential_duplicate",
                        message=f"This memory is very similar ({similarity:.0%}) to an existing one.",
                        related_memory_id=other_id,
                        related_memory_summary=other_summary,
                        confidence=similarity,
                        suggested_action=f"Use update_memory on '{other_id}' or link with 'supersedes'",
                    )
                )
            else:
                suggested_relation = self._infer_relation_type(
                    memory_type, other_type, content, other_summary or ""
                )
                reason = self._generate_link_reason(
                    memory_type, other_type, similarity, other_context
                )

                suggested_links.append(
                    SuggestedLink(
                        target_id=other_id,
                        target_summary=other_summary or "",
                        similarity=similarity,
                        suggested_relation=suggested_relation,
                        reason=reason,
                    )
                )

        # Check for potential contradictions
        content_lower = content.lower()
        has_contradiction_signals = any(
            kw in content_lower for kw in contradiction_keywords
        )

        if has_contradiction_signals and similar_memories:
            top_similar = similar_memories[0]
            if top_similar[2] > self._contradiction_threshold:
                insights.append(
                    KnowledgeInsight(
                        insight_type="potential_contradiction",
                        message="This memory may contradict existing knowledge.",
                        related_memory_id=top_similar[0],
                        related_memory_summary=top_similar[1],
                        confidence=0.6,
                        suggested_action="Review and link with 'supersedes' or 'contradicts'",
                    )
                )

        # Check for success after failure pattern
        if memory_type == MemoryType.SUCCESS:
            for other_id, other_summary, similarity, other_type, _ in similar_memories:
                if other_type == MemoryType.FAILURE.value and similarity > 0.6:
                    insights.append(
                        KnowledgeInsight(
                            insight_type="success_after_failure",
                            message="This success may resolve a previous failure.",
                            related_memory_id=other_id,
                            related_memory_summary=other_summary,
                            confidence=similarity,
                            suggested_action=f"Link to '{other_id}' with 'extends' relation",
                        )
                    )
                    break

        return suggested_links, insights

    def _infer_relation_type(
        self,
        new_type: MemoryType,
        existing_type: str,
        new_content: str,
        existing_summary: str,
    ) -> RelationType:
        """Infer the most likely relation type between two memories."""
        new_content_lower = new_content.lower()

        if new_type == MemoryType.SUCCESS:
            if existing_type in [MemoryType.INSIGHT.value, MemoryType.DECISION.value]:
                return RelationType.EXTENDS
            if existing_type == MemoryType.FAILURE.value:
                return RelationType.EXTENDS

        if (
            new_type == MemoryType.DECISION
            and existing_type == MemoryType.INSIGHT.value
        ):
            return RelationType.DEPENDS_ON

        supersede_keywords = [
            "updated",
            "new version",
            "replaces",
            "improved",
            "better approach",
        ]
        if any(kw in new_content_lower for kw in supersede_keywords):
            return RelationType.SUPERSEDES

        contradict_keywords = ["wrong", "incorrect", "actually", "contrary", "opposite"]
        if any(kw in new_content_lower for kw in contradict_keywords):
            return RelationType.CONTRADICTS

        return RelationType.RELATED

    def _generate_link_reason(
        self,
        new_type: MemoryType,
        existing_type: str,
        similarity: float,
        existing_context: str | None,
    ) -> str:
        """Generate a human-readable reason for a suggested link."""
        reasons = []

        if similarity > 0.85:
            reasons.append("Very high semantic similarity")
        elif similarity > 0.75:
            reasons.append("High semantic similarity")
        else:
            reasons.append("Moderate semantic similarity")

        if new_type == MemoryType.SUCCESS and existing_type == MemoryType.FAILURE.value:
            reasons.append("may be a solution to the recorded failure")
        elif (
            new_type == MemoryType.SUCCESS and existing_type == MemoryType.INSIGHT.value
        ):
            reasons.append("may be an application of this insight")
        elif (
            new_type == MemoryType.DECISION
            and existing_type == MemoryType.INSIGHT.value
        ):
            reasons.append("decision may be based on this insight")

        if existing_context:
            reasons.append(f"from project '{existing_context}'")

        return "; ".join(reasons)

    def recall_memories(
        self,
        query: str,
        limit: int = 5,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
        touch_on_recall: bool = True,
    ) -> tuple[list[MemoryWithContext], int]:
        """Recall memories using semantic search with hybrid scoring.

        Uses a hybrid scoring algorithm combining:
        - Vector similarity (semantic relevance)
        - Recency (time since last access)
        - Frequency (access count)

        Args:
            query: Search query.
            limit: Maximum results to return.
            context_filter: Optional filter by context/project.
            tag_filter: Optional filter by tags.
            type_filter: Optional filter by memory type.
            touch_on_recall: If True, update access metadata for returned memories.

        Returns:
            Tuple of (memories, total_found).
        """
        memories, total = self._repo.search_by_similarity(
            query=query,
            limit=limit,
            context_filter=context_filter,
            tag_filter=tag_filter,
            type_filter=type_filter,
            use_hybrid_scoring=True,
        )

        # Touch memories to update access metadata (for future recall scoring)
        if touch_on_recall and memories:
            memory_ids = [m.id for m in memories]
            self._repo.touch_memories(memory_ids)

        return memories, total

    def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
    ) -> tuple[list[MemoryWithContext], int, bool]:
        """List memories with pagination."""
        return self._repo.list_memories(
            limit=limit,
            offset=offset,
            context_filter=context_filter,
            tag_filter=tag_filter,
            type_filter=type_filter,
        )

    def get_memory(self, memory_id: str) -> MemoryWithContext | None:
        """Get a specific memory by ID."""
        return self._repo.get_by_id(memory_id)

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        memory_type: MemoryType | None = None,
    ) -> tuple[bool, list[str], str]:
        """Update an existing memory."""
        return self._repo.update_memory(
            memory_id=memory_id,
            content=content,
            tags=tags,
            memory_type=memory_type,
        )

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        return self._repo.delete_memory(memory_id)

    def link_memories(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        reason: str | None = None,
    ) -> None:
        """Create a link between two memories."""
        self._repo.create_link(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            reason=reason,
        )

    def unlink_memories(self, source_id: str, target_id: str) -> bool:
        """Remove a link between two memories."""
        return self._repo.delete_link(source_id, target_id)

    def get_memory_links(self, memory_id: str) -> list[MemoryLink]:
        """Get all outgoing links from a memory."""
        return self._repo.get_links(memory_id)

    def explore_related(
        self,
        memory_id: str,
        include_tag_siblings: bool = True,
        include_context_siblings: bool = True,
        max_per_category: int = 5,
    ) -> dict[str, list[MemoryWithContext]]:
        """Explore memories related to a given memory."""
        return self._repo.explore_related(
            memory_id=memory_id,
            include_tag_siblings=include_tag_siblings,
            include_context_siblings=include_context_siblings,
            max_per_category=max_per_category,
        )

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories."""
        return self._repo.get_stats()

    def analyze_knowledge(self) -> AnalyzeKnowledgeResult:
        """Analyze the knowledge base for health issues.

        Performs comprehensive health analysis including:
        - Orphan memories (no tags)
        - Unlinked memories (no RELATED_TO connections)
        - Stale memories (not updated recently)
        - Overall health score calculation
        """
        issues: list[KnowledgeHealthIssue] = []
        suggestions: list[str] = []
        stats: dict[str, Any] = {}

        memory_stats = self._repo.get_stats()
        total_memories = memory_stats.total_memories

        if total_memories == 0:
            return AnalyzeKnowledgeResult(
                total_memories=0,
                health_score=100.0,
                issues=[],
                suggestions=["Start storing memories to build your external brain!"],
                stats={},
            )

        # Check for orphan memories (no tags)
        orphan_memories = self._repo.get_orphan_memories(limit=10)
        if orphan_memories:
            issues.append(
                KnowledgeHealthIssue(
                    issue_type="orphan_memories",
                    severity="medium",
                    message=f"{len(orphan_memories)} memories have no tags.",
                    affected_memory_ids=[m[0] for m in orphan_memories],
                    suggested_action="Add tags using update_memory",
                )
            )

        # Check for unlinked memories
        unlinked_count = self._repo.get_unlinked_count()
        stats["unlinked_memories"] = unlinked_count

        if unlinked_count > 0 and total_memories > 5:
            link_ratio = unlinked_count / total_memories
            if link_ratio > 0.8:
                issues.append(
                    KnowledgeHealthIssue(
                        issue_type="low_connectivity",
                        severity="low",
                        message=f"{unlinked_count}/{total_memories} memories have no links.",
                        affected_memory_ids=[],
                        suggested_action="Use explore_related and link_memories",
                    )
                )

        # Check for stale memories
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=self._stale_days)
        stale_memories = self._repo.get_stale_memories(
            threshold=stale_threshold, limit=10
        )

        if stale_memories:
            issues.append(
                KnowledgeHealthIssue(
                    issue_type="stale_memories",
                    severity="low",
                    message=f"{len(stale_memories)}+ memories not updated in {self._stale_days}+ days.",
                    affected_memory_ids=[m[0] for m in stale_memories],
                    suggested_action="Review and update or mark as superseded",
                )
            )

        # Calculate health score
        health_score = self._calculate_health_score(
            issues, unlinked_count, total_memories
        )

        # Generate suggestions
        suggestions = self._generate_health_suggestions(
            issues, total_memories, memory_stats
        )

        return AnalyzeKnowledgeResult(
            total_memories=total_memories,
            health_score=health_score,
            issues=issues,
            suggestions=suggestions,
            stats=stats,
        )

    def _calculate_health_score(
        self,
        issues: list[KnowledgeHealthIssue],
        unlinked_count: int,
        total_memories: int,
    ) -> float:
        """Calculate overall health score based on issues."""
        health_score = 100.0
        for issue in issues:
            if issue.severity == "high":
                health_score -= 20
            elif issue.severity == "medium":
                health_score -= 10
            elif issue.severity == "low":
                health_score -= 5

        # Bonus for good link coverage
        if total_memories > 0 and unlinked_count / total_memories < 0.5:
            health_score = min(100, health_score + 5)

        return max(0, health_score)

    def _generate_health_suggestions(
        self,
        issues: list[KnowledgeHealthIssue],
        total_memories: int,
        memory_stats: MemoryStats,
    ) -> list[str]:
        """Generate improvement suggestions based on health analysis."""
        suggestions: list[str] = []

        if not issues:
            suggestions.append("Your knowledge base looks healthy!")
        else:
            suggestions.append("Address the issues above to improve discoverability.")

        if total_memories < 10:
            suggestions.append("Keep recording insights for better semantic search.")

        if memory_stats.memories_by_type.get(MemoryType.FAILURE.value, 0) == 0:
            suggestions.append("Don't forget to record failures too!")

        return suggestions

    # =========================================================================
    # Pattern Consolidation (Phase 2: Concept Abstraction)
    # =========================================================================

    def consolidate_patterns(
        self,
        tag_filter: str | None = None,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
    ) -> dict:
        """Extract patterns from clusters of similar memories.

        This implements the "Abstraction" mechanism that:
        1. Clusters memories by tag or high similarity
        2. Identifies common patterns/rules across the cluster
        3. Creates Pattern nodes and links instances

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
        clusters = self._find_memory_clusters(
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
                pattern_content = self._synthesize_pattern_content(cluster)
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

    def _find_memory_clusters(
        self,
        memories: list[MemoryWithContext],
        threshold: float,
        min_size: int,
    ) -> list[list[MemoryWithContext]]:
        """Find clusters of similar memories.

        Uses a simple greedy clustering approach.
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

    def _synthesize_pattern_content(
        self,
        cluster: list[MemoryWithContext],
    ) -> str | None:
        """Synthesize a pattern description from a cluster of memories.

        This is a simple heuristic approach. A more sophisticated version
        could use an LLM to generate the pattern.
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
