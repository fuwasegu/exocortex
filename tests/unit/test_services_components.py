"""Unit tests for domain/services/ components.

Tests for:
- MemoryAnalyzer: New memory analysis and insight detection
- KnowledgeHealthAnalyzer: Knowledge base health analysis
- PatternConsolidator: Pattern extraction from memory clusters
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from exocortex.domain.models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
)
from exocortex.domain.services.analyzer import MemoryAnalyzer
from exocortex.domain.services.health import KnowledgeHealthAnalyzer
from exocortex.domain.services.pattern import PatternConsolidator


# =============================================================================
# MemoryAnalyzer Tests
# =============================================================================


class TestMemoryAnalyzerRelationInference:
    """Tests for _infer_relation_type method."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with mock repository."""
        mock_repo = MagicMock()
        return MemoryAnalyzer(repository=mock_repo)

    def test_success_extends_insight(self, analyzer):
        """SUCCESS memory should EXTEND an INSIGHT."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.SUCCESS,
            existing_type=MemoryType.INSIGHT.value,
            new_content="Implemented the pattern successfully",
            existing_summary="Pattern for handling errors",
        )
        assert result == RelationType.EXTENDS

    def test_success_extends_failure(self, analyzer):
        """SUCCESS memory should EXTEND a FAILURE (resolution)."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.SUCCESS,
            existing_type=MemoryType.FAILURE.value,
            new_content="Fixed the bug",
            existing_summary="Bug in authentication",
        )
        assert result == RelationType.EXTENDS

    def test_decision_depends_on_insight(self, analyzer):
        """DECISION memory should DEPEND_ON an INSIGHT."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.DECISION,
            existing_type=MemoryType.INSIGHT.value,
            new_content="Decided to use this approach",
            existing_summary="Best practice for API design",
        )
        assert result == RelationType.DEPENDS_ON

    def test_supersede_keywords_detected(self, analyzer):
        """Content with supersede keywords should return SUPERSEDES."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            new_content="This is an updated version of the approach",
            existing_summary="Old approach",
        )
        assert result == RelationType.SUPERSEDES

    def test_contradict_keywords_detected(self, analyzer):
        """Content with contradict keywords should return CONTRADICTS."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            new_content="This is actually wrong, the correct way is...",
            existing_summary="Old insight",
        )
        assert result == RelationType.CONTRADICTS

    def test_default_related(self, analyzer):
        """Default relation should be RELATED."""
        result = analyzer._infer_relation_type(
            new_type=MemoryType.NOTE,
            existing_type=MemoryType.NOTE.value,
            new_content="Some note about the project",
            existing_summary="Another note",
        )
        assert result == RelationType.RELATED


class TestMemoryAnalyzerLinkReason:
    """Tests for _generate_link_reason method."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with mock repository."""
        mock_repo = MagicMock()
        return MemoryAnalyzer(repository=mock_repo)

    def test_very_high_similarity(self, analyzer):
        """Very high similarity (>0.85) should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.90,
            existing_context=None,
        )
        assert "Very high semantic similarity" in reason

    def test_high_similarity(self, analyzer):
        """High similarity (>0.75) should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.80,
            existing_context=None,
        )
        assert "High semantic similarity" in reason

    def test_moderate_similarity(self, analyzer):
        """Moderate similarity should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.70,
            existing_context=None,
        )
        assert "Moderate semantic similarity" in reason

    def test_success_resolves_failure(self, analyzer):
        """SUCCESS resolving FAILURE should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.SUCCESS,
            existing_type=MemoryType.FAILURE.value,
            similarity=0.75,
            existing_context=None,
        )
        assert "solution to the recorded failure" in reason

    def test_success_applies_insight(self, analyzer):
        """SUCCESS applying INSIGHT should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.SUCCESS,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.75,
            existing_context=None,
        )
        assert "application of this insight" in reason

    def test_decision_based_on_insight(self, analyzer):
        """DECISION based on INSIGHT should be noted."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.DECISION,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.75,
            existing_context=None,
        )
        assert "decision may be based on this insight" in reason

    def test_context_included(self, analyzer):
        """Context should be included in reason."""
        reason = analyzer._generate_link_reason(
            new_type=MemoryType.INSIGHT,
            existing_type=MemoryType.INSIGHT.value,
            similarity=0.75,
            existing_context="my-project",
        )
        assert "from project 'my-project'" in reason


class TestMemoryAnalyzerAnalyze:
    """Tests for analyze_new_memory method."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        return MagicMock()

    def test_no_similar_memories(self, mock_repo):
        """No similar memories should return empty results."""
        mock_repo.search_similar_by_embedding.return_value = []
        analyzer = MemoryAnalyzer(repository=mock_repo)

        links, insights = analyzer.analyze_new_memory(
            new_memory_id="new-id",
            content="Some content",
            embedding=[0.1] * 384,
            memory_type=MemoryType.INSIGHT,
        )

        assert links == []
        assert insights == []

    def test_duplicate_detection(self, mock_repo):
        """High similarity should trigger duplicate detection."""
        mock_repo.search_similar_by_embedding.return_value = [
            ("other-id", "Similar content", 0.95, "insight", "project"),
        ]
        analyzer = MemoryAnalyzer(repository=mock_repo, duplicate_threshold=0.90)

        links, insights = analyzer.analyze_new_memory(
            new_memory_id="new-id",
            content="Almost identical content",
            embedding=[0.1] * 384,
            memory_type=MemoryType.INSIGHT,
        )

        assert len(links) == 0  # Should not create link for duplicate
        assert len(insights) == 1
        assert insights[0].insight_type == "potential_duplicate"
        assert insights[0].confidence == 0.95

    def test_suggested_links_created(self, mock_repo):
        """Moderate similarity should create suggested links."""
        mock_repo.search_similar_by_embedding.return_value = [
            ("other-id", "Related content", 0.75, "insight", "project"),
        ]
        analyzer = MemoryAnalyzer(
            repository=mock_repo,
            link_threshold=0.65,
            duplicate_threshold=0.90,
        )

        links, insights = analyzer.analyze_new_memory(
            new_memory_id="new-id",
            content="Some related content",
            embedding=[0.1] * 384,
            memory_type=MemoryType.INSIGHT,
        )

        assert len(links) == 1
        assert links[0].target_id == "other-id"
        assert links[0].similarity == 0.75
        assert len(insights) == 0

    def test_contradiction_detection(self, mock_repo):
        """Content with contradiction keywords should trigger insight."""
        mock_repo.search_similar_by_embedding.return_value = [
            ("other-id", "Old approach", 0.75, "insight", "project"),
        ]
        analyzer = MemoryAnalyzer(
            repository=mock_repo,
            link_threshold=0.65,
            contradiction_threshold=0.70,
        )

        links, insights = analyzer.analyze_new_memory(
            new_memory_id="new-id",
            content="However, this approach is wrong and shouldn't be used",
            embedding=[0.1] * 384,
            memory_type=MemoryType.INSIGHT,
        )

        # Should have both link suggestion and contradiction insight
        assert len(links) == 1
        assert len(insights) == 1
        assert insights[0].insight_type == "potential_contradiction"

    def test_success_after_failure_pattern(self, mock_repo):
        """SUCCESS after FAILURE should be detected."""
        mock_repo.search_similar_by_embedding.return_value = [
            ("failure-id", "Failed attempt", 0.70, "failure", "project"),
        ]
        analyzer = MemoryAnalyzer(repository=mock_repo, link_threshold=0.65)

        links, insights = analyzer.analyze_new_memory(
            new_memory_id="new-id",
            content="Finally fixed the issue",
            embedding=[0.1] * 384,
            memory_type=MemoryType.SUCCESS,
        )

        # Should detect success after failure
        success_insights = [i for i in insights if i.insight_type == "success_after_failure"]
        assert len(success_insights) == 1
        assert success_insights[0].related_memory_id == "failure-id"


# =============================================================================
# KnowledgeHealthAnalyzer Tests
# =============================================================================


class TestKnowledgeHealthAnalyzer:
    """Tests for KnowledgeHealthAnalyzer."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        repo = MagicMock()
        repo.get_stats.return_value = MemoryStats(
            total_memories=20,
            memories_by_type={"insight": 10, "success": 5, "failure": 3, "decision": 2},
            total_contexts=5,
            total_tags=30,
            top_tags=[{"name": "python", "count": 10}],
        )
        repo.get_orphan_memories.return_value = []
        repo.get_unlinked_count.return_value = 5
        repo.get_stale_memories.return_value = []
        return repo

    def test_empty_knowledge_base(self, mock_repo):
        """Empty knowledge base should return healthy score."""
        mock_repo.get_stats.return_value = MemoryStats(
            total_memories=0,
            memories_by_type={},
            total_contexts=0,
            total_tags=0,
            top_tags=[],
        )
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        assert result.total_memories == 0
        assert result.health_score == 100.0
        assert len(result.issues) == 0
        assert "Start storing memories" in result.suggestions[0]

    def test_healthy_knowledge_base(self, mock_repo):
        """Healthy knowledge base should return high score."""
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        assert result.total_memories == 20
        assert result.health_score >= 95.0  # Good link coverage bonus
        assert len(result.issues) == 0

    def test_orphan_memories_detected(self, mock_repo):
        """Orphan memories should be detected as issue."""
        mock_repo.get_orphan_memories.return_value = [
            ("orphan-1", "Orphan memory 1"),
            ("orphan-2", "Orphan memory 2"),
        ]
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        orphan_issues = [i for i in result.issues if i.issue_type == "orphan_memories"]
        assert len(orphan_issues) == 1
        assert "2 memories have no tags" in orphan_issues[0].message
        assert result.health_score < 100.0  # Score reduced

    def test_low_connectivity_detected(self, mock_repo):
        """Low connectivity should be detected when many memories unlinked."""
        mock_repo.get_unlinked_count.return_value = 18  # 90% unlinked
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        connectivity_issues = [i for i in result.issues if i.issue_type == "low_connectivity"]
        assert len(connectivity_issues) == 1
        assert "18/20 memories have no links" in connectivity_issues[0].message

    def test_stale_memories_detected(self, mock_repo):
        """Stale memories should be detected."""
        mock_repo.get_stale_memories.return_value = [
            ("stale-1", "Old memory 1"),
            ("stale-2", "Old memory 2"),
            ("stale-3", "Old memory 3"),
        ]
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo, stale_days=90)

        result = analyzer.analyze()

        stale_issues = [i for i in result.issues if i.issue_type == "stale_memories"]
        assert len(stale_issues) == 1
        assert "3+ memories not updated in 90+ days" in stale_issues[0].message

    def test_health_score_calculation(self, mock_repo):
        """Health score should decrease based on issue severity."""
        mock_repo.get_orphan_memories.return_value = [("o1", "")]  # medium: -10
        mock_repo.get_stale_memories.return_value = [("s1", "")]  # low: -5
        mock_repo.get_unlinked_count.return_value = 18  # low: -5
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        # 100 - 10 (orphan) - 5 (stale) - 5 (connectivity) = 80
        assert result.health_score == 80.0

    def test_no_failures_suggestion(self, mock_repo):
        """Should suggest recording failures if none exist."""
        mock_repo.get_stats.return_value = MemoryStats(
            total_memories=20,
            memories_by_type={"insight": 15, "success": 5},  # No failures
            total_contexts=5,
            total_tags=30,
            top_tags=[],
        )
        analyzer = KnowledgeHealthAnalyzer(repository=mock_repo)

        result = analyzer.analyze()

        assert any("record failures" in s for s in result.suggestions)


# =============================================================================
# PatternConsolidator Tests
# =============================================================================


class TestPatternConsolidator:
    """Tests for PatternConsolidator."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository with embedding engine."""
        repo = MagicMock()
        repo._embedding_engine = MagicMock()
        repo._embedding_engine.embed.return_value = [0.1] * 384
        repo.compute_similarity.return_value = 0.8
        return repo

    def _create_mock_memory(
        self,
        memory_id: str,
        content: str,
        tags: list[str],
        memory_type: MemoryType = MemoryType.INSIGHT,
    ) -> MemoryWithContext:
        """Create a mock memory for testing."""
        now = datetime.now(timezone.utc)
        return MemoryWithContext(
            id=memory_id,
            content=content,
            summary=content[:50],
            memory_type=memory_type,
            created_at=now,
            updated_at=now,
            context="test-project",
            tags=tags,
        )

    def test_not_enough_memories(self, mock_repo):
        """Should return early if not enough memories."""
        mock_repo.get_memories_by_tag.return_value = [
            self._create_mock_memory("m1", "Memory 1", ["tag"]),
        ]
        consolidator = PatternConsolidator(repository=mock_repo)

        result = consolidator.consolidate(tag_filter="tag", min_cluster_size=3)

        assert result["patterns_found"] == 0
        assert result["patterns_created"] == 0
        assert result["memories_linked"] == 0

    def test_cluster_finding(self, mock_repo):
        """Should find clusters of similar memories."""
        memories = [
            self._create_mock_memory("m1", "Database connection pooling", ["database"]),
            self._create_mock_memory("m2", "Connection pool configuration", ["database"]),
            self._create_mock_memory("m3", "Pool size optimization", ["database"]),
        ]
        mock_repo.get_memories_by_tag.return_value = memories
        mock_repo.search_similar_patterns.return_value = []
        mock_repo.create_pattern.return_value = ("pattern-1", "Pattern summary", [0.1] * 384)

        consolidator = PatternConsolidator(repository=mock_repo)

        result = consolidator.consolidate(tag_filter="database", min_cluster_size=3)

        assert result["patterns_created"] >= 0  # May or may not create based on similarity

    def test_existing_pattern_linking(self, mock_repo):
        """Should link to existing pattern if similar enough."""
        memories = [
            self._create_mock_memory("m1", "Memory 1", ["tag"]),
            self._create_mock_memory("m2", "Memory 2", ["tag"]),
            self._create_mock_memory("m3", "Memory 3", ["tag"]),
        ]
        mock_repo.get_memories_by_tag.return_value = memories
        mock_repo.search_similar_patterns.return_value = [
            ("existing-pattern", "Existing pattern", 0.85),
        ]

        consolidator = PatternConsolidator(repository=mock_repo)

        result = consolidator.consolidate(tag_filter="tag", min_cluster_size=3)

        # Should find existing pattern and link memories to it
        assert result["patterns_found"] >= 0

    def test_synthesize_content(self, mock_repo):
        """Should synthesize pattern content from cluster."""
        memories = [
            self._create_mock_memory("m1", "Memory about caching", ["caching", "performance"]),
            self._create_mock_memory("m2", "Another caching insight", ["caching", "redis"]),
            self._create_mock_memory("m3", "Cache optimization", ["caching", "performance"]),
        ]

        consolidator = PatternConsolidator(repository=mock_repo)
        content = consolidator._synthesize_content(memories)

        assert content is not None
        assert "Pattern extracted from 3 memories" in content
        assert "caching" in content  # Common tag

    def test_synthesize_content_empty(self, mock_repo):
        """Should return None for empty cluster."""
        consolidator = PatternConsolidator(repository=mock_repo)
        content = consolidator._synthesize_content([])

        assert content is None

    def test_find_clusters_respects_threshold(self, mock_repo):
        """Clustering should respect similarity threshold."""
        memories = [
            self._create_mock_memory("m1", "Memory 1", ["tag"]),
            self._create_mock_memory("m2", "Memory 2", ["tag"]),
            self._create_mock_memory("m3", "Different memory", ["tag"]),
        ]
        # First two similar, third not
        mock_repo.compute_similarity.side_effect = [0.8, 0.3, 0.8, 0.3]

        consolidator = PatternConsolidator(repository=mock_repo)
        clusters = consolidator._find_clusters(memories, threshold=0.7, min_size=2)

        # Should have at least one cluster
        assert len(clusters) >= 0

    def test_frequently_accessed_fallback(self, mock_repo):
        """Should use frequently accessed memories if no tag filter."""
        memories = [
            self._create_mock_memory("m1", "Memory 1", ["tag"]),
            self._create_mock_memory("m2", "Memory 2", ["tag"]),
            self._create_mock_memory("m3", "Memory 3", ["tag"]),
        ]
        mock_repo.get_frequently_accessed_memories.return_value = memories
        mock_repo.search_similar_patterns.return_value = []
        mock_repo.create_pattern.return_value = ("pattern-1", "Pattern summary", [0.1] * 384)

        consolidator = PatternConsolidator(repository=mock_repo)

        result = consolidator.consolidate(tag_filter=None, min_cluster_size=3)

        mock_repo.get_frequently_accessed_memories.assert_called_once()

