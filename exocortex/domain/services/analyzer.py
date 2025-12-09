"""Memory Analyzer - Analyzes new memories for insights and links.

This module implements the analysis logic that detects:
- Potential duplicate memories
- Possible contradictions
- Success after failure patterns
- Suggested links between related memories
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import (
    KnowledgeInsight,
    MemoryType,
    RelationType,
    SuggestedLink,
)

if TYPE_CHECKING:
    from ...infra.repositories import MemoryRepository


class MemoryAnalyzer:
    """Analyzes new memories for potential links and insights."""

    # Keywords that suggest content might contradict existing knowledge
    CONTRADICTION_KEYWORDS = [
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

    # Keywords that suggest content supersedes existing knowledge
    SUPERSEDE_KEYWORDS = [
        "updated",
        "new version",
        "replaces",
        "improved",
        "better approach",
    ]

    # Keywords that suggest content contradicts existing knowledge
    CONTRADICT_KEYWORDS = [
        "wrong",
        "incorrect",
        "actually",
        "contrary",
        "opposite",
    ]

    def __init__(
        self,
        repository: MemoryRepository,
        link_threshold: float = 0.65,
        duplicate_threshold: float = 0.90,
        contradiction_threshold: float = 0.70,
    ) -> None:
        """Initialize the analyzer.

        Args:
            repository: Memory repository for data access.
            link_threshold: Similarity threshold for suggesting links.
            duplicate_threshold: Similarity threshold for duplicate detection.
            contradiction_threshold: Similarity threshold for contradiction check.
        """
        self._repo = repository
        self._link_threshold = link_threshold
        self._duplicate_threshold = duplicate_threshold
        self._contradiction_threshold = contradiction_threshold

    def analyze_new_memory(
        self,
        new_memory_id: str,
        content: str,
        embedding: list[float],
        memory_type: MemoryType,
    ) -> tuple[list[SuggestedLink], list[KnowledgeInsight]]:
        """Analyze a new memory for potential links and insights.

        Uses KùzuDB's native vector search for efficient similarity lookup.

        Args:
            new_memory_id: ID of the newly created memory.
            content: Content of the new memory.
            embedding: Embedding vector of the new memory.
            memory_type: Type of the new memory.

        Returns:
            Tuple of (suggested_links, insights).
        """
        suggested_links: list[SuggestedLink] = []
        insights: list[KnowledgeInsight] = []

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
            kw in content_lower for kw in self.CONTRADICTION_KEYWORDS
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
        """Infer the most likely relation type between two memories.

        Args:
            new_type: Type of the new memory.
            existing_type: Type of the existing memory (as string).
            new_content: Content of the new memory.
            existing_summary: Summary of the existing memory.

        Returns:
            Inferred relation type.
        """
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

        if any(kw in new_content_lower for kw in self.SUPERSEDE_KEYWORDS):
            return RelationType.SUPERSEDES

        if any(kw in new_content_lower for kw in self.CONTRADICT_KEYWORDS):
            return RelationType.CONTRADICTS

        return RelationType.RELATED

    def _generate_link_reason(
        self,
        new_type: MemoryType,
        existing_type: str,
        similarity: float,
        existing_context: str | None,
    ) -> str:
        """Generate a human-readable reason for a suggested link.

        Args:
            new_type: Type of the new memory.
            existing_type: Type of the existing memory (as string).
            similarity: Similarity score between memories.
            existing_context: Context of the existing memory.

        Returns:
            Human-readable reason string.
        """
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
