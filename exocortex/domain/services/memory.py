"""Memory Service - Core business logic for Exocortex.

This is the main service class that coordinates memory operations.
It delegates specialized logic to:
- MemoryAnalyzer: New memory analysis and insight detection
- KnowledgeHealthAnalyzer: Knowledge base health analysis
- PatternConsolidator: Pattern extraction from memory clusters
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import ValidationError
from ..models import (
    AnalyzeKnowledgeResult,
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
    StoreMemoryResult,
)
from .analyzer import MemoryAnalyzer
from .health import KnowledgeHealthAnalyzer
from .pattern import PatternConsolidator

if TYPE_CHECKING:
    from ...infra.repositories import MemoryRepository


class MemoryService:
    """Service for memory-related business logic.

    This class acts as a facade/coordinator, delegating specialized
    logic to dedicated analyzer classes while maintaining a simple
    public interface.
    """

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
        self._max_tags = max_tags

        # Initialize specialized analyzers
        self._memory_analyzer = MemoryAnalyzer(
            repository=repository,
            link_threshold=link_threshold,
            duplicate_threshold=duplicate_threshold,
            contradiction_threshold=contradiction_threshold,
        )
        self._health_analyzer = KnowledgeHealthAnalyzer(
            repository=repository,
            stale_days=stale_days,
        )
        self._pattern_consolidator = PatternConsolidator(
            repository=repository,
        )

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

    # =========================================================================
    # Memory CRUD Operations
    # =========================================================================

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

        suggested_links = []
        insights = []

        if auto_analyze:
            suggested_links, insights = self._memory_analyzer.analyze_new_memory(
                memory_id, content, embedding, memory_type
            )

        return StoreMemoryResult(
            success=True,
            memory_id=memory_id,
            summary=summary,
            suggested_links=suggested_links,
            insights=insights,
        )

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

    # =========================================================================
    # Link Operations
    # =========================================================================

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

    # =========================================================================
    # Statistics and Health
    # =========================================================================

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories."""
        return self._repo.get_stats()

    def analyze_knowledge(self) -> AnalyzeKnowledgeResult:
        """Analyze the knowledge base for health issues.

        Delegates to KnowledgeHealthAnalyzer.
        """
        return self._health_analyzer.analyze()

    # =========================================================================
    # Pattern Consolidation
    # =========================================================================

    def consolidate_patterns(
        self,
        tag_filter: str | None = None,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
    ) -> dict:
        """Extract patterns from clusters of similar memories.

        Delegates to PatternConsolidator.

        Args:
            tag_filter: Optional tag to focus pattern extraction.
            min_cluster_size: Minimum memories to form a pattern.
            similarity_threshold: Minimum similarity for clustering.

        Returns:
            Summary of patterns found/created.
        """
        return self._pattern_consolidator.consolidate(
            tag_filter=tag_filter,
            min_cluster_size=min_cluster_size,
            similarity_threshold=similarity_threshold,
        )

