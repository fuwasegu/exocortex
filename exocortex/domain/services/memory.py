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
from .curiosity import CuriosityEngine, CuriosityReport
from .health import KnowledgeHealthAnalyzer
from .pattern import PatternConsolidator

if TYPE_CHECKING:
    from ...infra.repositories import MemoryRepository
    from ..models import SessionBriefing, SuggestedAction


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
        self._curiosity_engine = CuriosityEngine(
            repository=repository,
            contradiction_threshold=contradiction_threshold,
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

    # =========================================================================
    # Curiosity Engine
    # =========================================================================

    def curiosity_scan(
        self,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        max_findings: int = 10,
    ) -> CuriosityReport:
        """Scan the knowledge base for interesting findings.

        The Curiosity Engine looks for:
        - Contradictions between memories
        - Outdated knowledge that may need revision
        - Knowledge gaps that could be filled

        Delegates to CuriosityEngine.

        Args:
            context_filter: Optional context to focus on.
            tag_filter: Optional tags to focus on.
            max_findings: Maximum findings per category.

        Returns:
            CuriosityReport with findings and questions.
        """
        return self._curiosity_engine.scan(
            context_filter=context_filter,
            tag_filter=tag_filter,
            max_findings=max_findings,
        )

    # =========================================================================
    # Session Briefing
    # =========================================================================

    def get_session_briefing(
        self,
        context_filter: str | None = None,
    ) -> SessionBriefing:
        """Get a briefing for the start of a session.

        Provides context about the current state of the knowledge base
        and suggests actions to take.

        Args:
            context_filter: Optional context to focus on.

        Returns:
            SessionBriefing with current state and suggested actions.
        """
        from ..models import SessionBriefing

        # 1. Get recent memories
        recent_memories_raw, total_count, _ = self._repo.list_memories(
            limit=5,
            context_filter=context_filter,
        )
        recent_memories = [
            {
                "id": m.id,
                "summary": m.summary[:100] + "..."
                if len(m.summary) > 100
                else m.summary,
                "type": m.memory_type.value,
                "created_at": m.created_at.isoformat(),
                "context": m.context,
            }
            for m in recent_memories_raw
        ]

        # 2. Get health status
        health_result = self._health_analyzer.analyze()
        health_score = health_result.health_score
        health_summary = self._get_health_summary(health_score, health_result.issues)

        # 3. Run curiosity scan for issues
        curiosity_report = self._curiosity_engine.scan(
            context_filter=context_filter,
            max_findings=5,
        )
        pending_issues = self._extract_pending_issues(curiosity_report)

        # 4. Get context summary (from repository stats)
        try:
            repo_stats = self._repo.get_stats()
            context_summary = {}
            # MemoryStats is a Pydantic model, access via attributes
            if hasattr(repo_stats, "memories_by_type"):
                # Use memories_by_type as a proxy for context info
                context_summary = {"total": repo_stats.total_memories}
        except Exception:
            context_summary = {}

        # 5. Generate suggested actions
        suggested_actions = self._generate_suggested_actions(
            health_score=health_score,
            health_issues=health_result.issues,
            curiosity_report=curiosity_report,
            total_count=total_count,
            context_filter=context_filter,
        )

        return SessionBriefing(
            recent_memories=recent_memories,
            total_memories=total_count,
            health_score=health_score,
            health_summary=health_summary,
            pending_issues=pending_issues,
            suggested_actions=suggested_actions,
            context_summary=context_summary,
        )

    def _get_health_summary(
        self,
        health_score: float,
        issues: list,
    ) -> str:
        """Generate a brief health summary."""
        if health_score >= 90:
            return "✨ Excellent - Knowledge base is well-organized"
        elif health_score >= 70:
            return "👍 Good - Minor improvements possible"
        elif health_score >= 50:
            return "⚠️ Fair - Some attention needed"
        else:
            issue_count = len(issues)
            return f"🔴 Needs attention - {issue_count} issue(s) detected"

    def _extract_pending_issues(
        self,
        curiosity_report: CuriosityReport,
    ) -> list[dict]:
        """Extract pending issues from curiosity report."""
        issues = []

        for contradiction in curiosity_report.contradictions[:3]:
            issues.append(
                {
                    "type": "contradiction",
                    "severity": "high",
                    "description": contradiction.reason,
                    "memory_ids": [
                        contradiction.memory_a_id,
                        contradiction.memory_b_id,
                    ],
                }
            )

        for outdated in curiosity_report.outdated_knowledge[:3]:
            issues.append(
                {
                    "type": "outdated",
                    "severity": "medium",
                    "description": outdated.reason,
                    "memory_ids": [outdated.memory_id],
                }
            )

        return issues

    def _generate_suggested_actions(
        self,
        health_score: float,
        health_issues: list,
        curiosity_report: CuriosityReport,
        total_count: int,
        context_filter: str | None,
    ) -> list[SuggestedAction]:
        """Generate suggested actions based on current state."""
        from ..models import SuggestedAction

        actions: list[SuggestedAction] = []

        # Always suggest recall if there are memories
        if total_count > 0:
            actions.append(
                SuggestedAction(
                    tool="exo_recall_memories",
                    priority="low",
                    reason="Search existing knowledge before creating new memories",
                    parameters={"limit": 5},
                )
            )

        # Contradictions need resolution
        if curiosity_report.contradictions:
            first = curiosity_report.contradictions[0]
            actions.append(
                SuggestedAction(
                    tool="exo_link_memories",
                    priority="high",
                    reason=f"Resolve contradiction: {first.reason[:50]}...",
                    parameters={
                        "source_id": first.memory_a_id,
                        "target_id": first.memory_b_id,
                        "relation_type": "supersedes",
                    },
                )
            )

        # Outdated knowledge needs review
        if curiosity_report.outdated_knowledge:
            first = curiosity_report.outdated_knowledge[0]
            actions.append(
                SuggestedAction(
                    tool="exo_get_memory",
                    priority="medium",
                    reason=f"Review potentially outdated: {first.reason[:50]}...",
                    parameters={"memory_id": first.memory_id},
                )
            )

        # Health issues
        orphan_issue = next(
            (i for i in health_issues if i.issue_type == "orphan_memories"),
            None,
        )
        if orphan_issue:
            actions.append(
                SuggestedAction(
                    tool="exo_analyze_knowledge",
                    priority="medium",
                    reason=f"Found {orphan_issue.count} orphan memories without tags",
                    parameters={},
                )
            )

        # If everything is clean and enough memories, suggest exploration
        is_clean = not actions or (len(actions) == 1 and actions[0].priority == "low")
        if is_clean and total_count > 10:
            actions.append(
                SuggestedAction(
                    tool="exo_consolidate",
                    priority="low",
                    reason="Extract patterns from your knowledge base",
                    parameters={},
                )
            )

        return actions
