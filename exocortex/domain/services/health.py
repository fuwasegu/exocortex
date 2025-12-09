"""Knowledge Health Analyzer - Analyzes knowledge base health.

This module implements the health analysis logic that detects:
- Orphan memories (no tags)
- Unlinked memories (no relationships)
- Stale memories (not updated recently)
- Overall health score calculation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    MemoryStats,
    MemoryType,
)

if TYPE_CHECKING:
    from ...infra.repositories import MemoryRepository


class KnowledgeHealthAnalyzer:
    """Analyzes knowledge base for health issues and improvements."""

    def __init__(
        self,
        repository: MemoryRepository,
        stale_days: int = 90,
    ) -> None:
        """Initialize the analyzer.

        Args:
            repository: Memory repository for data access.
            stale_days: Days after which a memory is considered stale.
        """
        self._repo = repository
        self._stale_days = stale_days

    def analyze(self) -> AnalyzeKnowledgeResult:
        """Analyze the knowledge base for health issues.

        Performs comprehensive health analysis including:
        - Orphan memories (no tags)
        - Unlinked memories (no RELATED_TO connections)
        - Stale memories (not updated recently)
        - Overall health score calculation

        Returns:
            AnalyzeKnowledgeResult with health score, issues, and suggestions.
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
        suggestions = self._generate_suggestions(issues, total_memories, memory_stats)

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
        """Calculate overall health score based on issues.

        Args:
            issues: List of detected health issues.
            unlinked_count: Number of memories without links.
            total_memories: Total number of memories.

        Returns:
            Health score from 0 to 100.
        """
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

    def _generate_suggestions(
        self,
        issues: list[KnowledgeHealthIssue],
        total_memories: int,
        memory_stats: MemoryStats,
    ) -> list[str]:
        """Generate improvement suggestions based on health analysis.

        Args:
            issues: List of detected health issues.
            total_memories: Total number of memories.
            memory_stats: Memory statistics.

        Returns:
            List of suggestion strings.
        """
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
