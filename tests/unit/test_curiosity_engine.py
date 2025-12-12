"""Unit tests for CuriosityEngine.

Tests for:
- Contradiction detection between memories
- Outdated knowledge detection
- Question generation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from exocortex.domain.services.curiosity import (
    Contradiction,
    CuriosityEngine,
    CuriosityReport,
    OutdatedKnowledge,
    SuggestedLink,
)


class TestCuriosityEngineContradictionDetection:
    """Tests for contradiction detection logic."""

    @pytest.fixture
    def engine(self):
        """Create engine with mock repository."""
        mock_repo = MagicMock()
        return CuriosityEngine(repository=mock_repo)

    @pytest.fixture
    def mock_memory_success(self):
        """Create a mock success memory."""
        mem = MagicMock()
        mem.id = "mem-success-1"
        mem.summary = "This approach works perfectly"
        mem.content = "The solution works and is recommended"
        mem.memory_type = "success"
        mem.tags = ["database", "optimization"]
        return mem

    @pytest.fixture
    def mock_memory_failure(self):
        """Create a mock failure memory."""
        mem = MagicMock()
        mem.id = "mem-failure-1"
        mem.summary = "This approach failed badly"
        mem.content = "The solution doesn't work and should be avoided"
        mem.memory_type = "failure"
        mem.tags = ["database", "optimization"]
        return mem

    def test_detects_type_contradiction(
        self, engine, mock_memory_success, mock_memory_failure
    ):
        """SUCCESS vs FAILURE on same tags should be detected."""
        contradiction = engine._check_contradiction(
            mock_memory_success, mock_memory_failure
        )

        assert contradiction is not None
        assert contradiction.memory_a_id == "mem-success-1"
        assert contradiction.memory_b_id == "mem-failure-1"
        assert "success vs failure" in contradiction.reason.lower()
        assert contradiction.confidence >= 0.5

    def test_detects_keyword_contradiction(self, engine):
        """Contradictory keywords should be detected."""
        mem_a = MagicMock()
        mem_a.id = "mem-a"
        mem_a.summary = "This solution always works"
        mem_a.content = "The best approach is to always use caching"
        mem_a.memory_type = "insight"
        mem_a.tags = ["caching"]

        mem_b = MagicMock()
        mem_b.id = "mem-b"
        mem_b.summary = "Avoid this approach"
        mem_b.content = "Never use this pattern, it's wrong"
        mem_b.memory_type = "insight"
        mem_b.tags = ["caching"]

        contradiction = engine._check_contradiction(mem_a, mem_b)

        assert contradiction is not None
        assert "contradictory sentiment" in contradiction.reason.lower()

    def test_no_contradiction_for_unrelated_memories(self, engine):
        """Memories with no shared tags shouldn't be flagged."""
        mem_a = MagicMock()
        mem_a.id = "mem-a"
        mem_a.summary = "Database tip"
        mem_a.content = "Use indexes for performance"
        mem_a.memory_type = "insight"
        mem_a.tags = ["database"]

        mem_b = MagicMock()
        mem_b.id = "mem-b"
        mem_b.summary = "Frontend tip"
        mem_b.content = "Use React hooks"
        mem_b.memory_type = "insight"
        mem_b.tags = ["frontend"]

        contradiction = engine._check_contradiction(mem_a, mem_b)

        # Low confidence due to no shared context
        assert contradiction is None or contradiction.confidence < 0.5

    def test_shared_tags_increase_confidence(self, engine):
        """Memories sharing tags should have higher confidence."""
        mem_a = MagicMock()
        mem_a.id = "mem-a"
        mem_a.summary = "Works"
        mem_a.content = "This always works"
        mem_a.memory_type = "success"
        mem_a.tags = ["api", "rest", "design"]

        mem_b = MagicMock()
        mem_b.id = "mem-b"
        mem_b.summary = "Doesn't work"
        mem_b.content = "This never works"
        mem_b.memory_type = "failure"
        mem_b.tags = ["api", "rest", "design"]

        contradiction = engine._check_contradiction(mem_a, mem_b)

        assert contradiction is not None
        assert "shared tags" in contradiction.reason.lower()

    def test_detects_japanese_keyword_contradiction(self, engine):
        """Japanese contradictory keywords should be detected."""
        mem_a = MagicMock()
        mem_a.id = "mem-a"
        mem_a.summary = "成功したアプローチ"
        mem_a.content = "この方法で解決できた。推奨する。"
        mem_a.memory_type = "insight"
        mem_a.tags = ["database"]

        mem_b = MagicMock()
        mem_b.id = "mem-b"
        mem_b.summary = "失敗したアプローチ"
        mem_b.content = "この方法はダメだった。バグが発生する。"
        mem_b.memory_type = "insight"
        mem_b.tags = ["database"]

        contradiction = engine._check_contradiction(mem_a, mem_b)

        assert contradiction is not None
        assert "contradictory sentiment" in contradiction.reason.lower()


class TestCuriosityEngineOutdatedDetection:
    """Tests for outdated knowledge detection."""

    @pytest.fixture
    def engine(self):
        """Create engine with mock repository."""
        mock_repo = MagicMock()
        return CuriosityEngine(repository=mock_repo, stale_days=90)

    def test_detects_stale_unsuperseded_memories(self, engine):
        """Old memories of type insight/decision that haven't been superseded should be flagged."""
        # Setup mock - a stale insight memory
        old_memory = MagicMock()
        old_memory.id = "old-mem"
        old_memory.summary = "Old architecture decision"
        old_memory.memory_type = "decision"
        old_memory.created_at = datetime.now(timezone.utc) - timedelta(days=120)
        old_memory.updated_at = datetime.now(timezone.utc) - timedelta(days=120)

        # list_memories returns 3 values: (memories, total_count, has_more)
        engine._repo.list_memories.return_value = ([old_memory], 1, False)
        # No supersedes links
        engine._repo.get_links.return_value = []

        outdated = engine._find_outdated_knowledge(None, 10)

        assert len(outdated) == 1
        assert outdated[0].memory_id == "old-mem"
        assert outdated[0].days_since_update >= 90

    def test_ignores_recent_memories(self, engine):
        """Recent memories should not be flagged as outdated."""
        recent_memory = MagicMock()
        recent_memory.id = "recent-mem"
        recent_memory.summary = "Recent decision"
        recent_memory.memory_type = "decision"
        recent_memory.created_at = datetime.now(timezone.utc) - timedelta(days=10)
        recent_memory.updated_at = datetime.now(timezone.utc) - timedelta(days=10)

        engine._repo.list_memories.return_value = ([recent_memory], 1, False)

        outdated = engine._find_outdated_knowledge(None, 10)

        assert len(outdated) == 0


class TestCuriosityEngineQuestionGeneration:
    """Tests for question generation."""

    @pytest.fixture
    def engine(self):
        """Create engine with mock repository."""
        mock_repo = MagicMock()
        return CuriosityEngine(repository=mock_repo)

    def test_generates_contradiction_question(self, engine):
        """Should generate question when contradictions found."""
        report = CuriosityReport(
            contradictions=[
                Contradiction(
                    memory_a_id="a",
                    memory_a_summary="A",
                    memory_b_id="b",
                    memory_b_summary="B",
                    similarity=0.8,
                    reason="test",
                    confidence=0.7,
                )
            ]
        )

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        # Check for Japanese message (矛盾 = contradiction)
        assert "矛盾" in questions[0]

    def test_generates_outdated_question(self, engine):
        """Should generate question when outdated knowledge found."""
        report = CuriosityReport(
            outdated_knowledge=[
                OutdatedKnowledge(
                    memory_id="old",
                    summary="Old stuff",
                    superseded_by_id=None,
                    superseded_by_summary=None,
                    reason="test",
                    days_since_update=100,
                )
            ]
        )

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        # Check for Japanese message (古くなった = outdated)
        assert "古くなった" in questions[0]

    def test_generates_positive_message_when_clean(self, engine):
        """Should generate positive message when no issues found."""
        report = CuriosityReport()

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        # Check for Japanese message (一貫 = consistent)
        assert "一貫" in questions[0]


class TestCuriosityEngineSuggestedLinks:
    """Tests for suggested link detection."""

    @pytest.fixture
    def engine(self):
        """Create engine with mock repository."""
        mock_repo = MagicMock()
        mock_repo.get_links.return_value = []
        return CuriosityEngine(repository=mock_repo)

    @pytest.fixture
    def mock_memories_shared_tags(self):
        """Create memories with shared tags."""
        mem_a = MagicMock()
        mem_a.id = "mem-a"
        mem_a.summary = "Database optimization technique"
        mem_a.content = "Use connection pooling for better performance"
        mem_a.memory_type = "insight"
        mem_a.context_name = "project-a"
        mem_a.tags = ["database", "performance", "optimization"]

        mem_b = MagicMock()
        mem_b.id = "mem-b"
        mem_b.summary = "Query optimization approach"
        mem_b.content = "Index frequently queried columns"
        mem_b.memory_type = "insight"
        mem_b.context_name = "project-b"
        mem_b.tags = ["database", "performance", "sql"]

        return [mem_a, mem_b]

    @pytest.fixture
    def mock_memories_same_context(self):
        """Create memories in same context with same type."""
        mem_a = MagicMock()
        mem_a.id = "mem-c"
        mem_a.summary = "API design decision"
        mem_a.content = "Use REST for public API"
        mem_a.memory_type = "decision"
        mem_a.context_name = "backend-project"
        mem_a.tags = ["api"]

        mem_b = MagicMock()
        mem_b.id = "mem-d"
        mem_b.summary = "Authentication decision"
        mem_b.content = "Use JWT tokens"
        mem_b.memory_type = "decision"
        mem_b.context_name = "backend-project"
        mem_b.tags = ["auth"]

        return [mem_a, mem_b]

    def test_finds_tag_shared_links(self, engine, mock_memories_shared_tags):
        """Memories with 2+ shared tags should be suggested as links."""
        engine._repo.list_memories.return_value = (mock_memories_shared_tags, 2, False)

        suggestions = engine._find_tag_shared_links(
            mock_memories_shared_tags, set(), set(), 10
        )

        assert len(suggestions) == 1
        assert suggestions[0].link_type == "tag_shared"
        assert (
            "database" in suggestions[0].reason
            or "performance" in suggestions[0].reason
        )
        assert suggestions[0].confidence >= 0.5

    def test_finds_context_shared_links(self, engine, mock_memories_same_context):
        """Memories in same context with same type should be suggested."""
        suggestions = engine._find_context_shared_links(
            mock_memories_same_context, set(), set(), 10
        )

        assert len(suggestions) == 1
        assert suggestions[0].link_type == "context_shared"
        assert "backend-project" in suggestions[0].reason
        assert "decision" in suggestions[0].reason

    def test_skips_already_linked_memories(self, engine, mock_memories_shared_tags):
        """Should not suggest links for already linked memories."""
        existing_links = {("mem-a", "mem-b")}

        suggestions = engine._find_tag_shared_links(
            mock_memories_shared_tags, existing_links, set(), 10
        )

        assert len(suggestions) == 0

    def test_generates_link_question(self, engine):
        """Should generate question when suggested links found."""
        report = CuriosityReport(
            suggested_links=[
                SuggestedLink(
                    source_id="a",
                    source_summary="A",
                    target_id="b",
                    target_summary="B",
                    reason="Share 2 tags",
                    link_type="tag_shared",
                    confidence=0.7,
                )
            ]
        )

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        assert "リンク" in questions[0]


class TestCuriosityReportSerialization:
    """Tests for CuriosityReport serialization."""

    def test_to_dict_empty_report(self):
        """Empty report should serialize correctly."""
        report = CuriosityReport()
        result = report.to_dict()

        assert result["contradictions"] == []
        assert result["outdated_knowledge"] == []
        assert result["knowledge_gaps"] == []
        assert result["suggested_links"] == []
        assert result["questions"] == []

    def test_to_dict_with_data(self):
        """Report with data should serialize all fields."""
        report = CuriosityReport(
            contradictions=[
                Contradiction(
                    memory_a_id="a",
                    memory_a_summary="Summary A",
                    memory_b_id="b",
                    memory_b_summary="Summary B",
                    similarity=0.8,
                    reason="Test reason",
                    confidence=0.75,
                )
            ],
            suggested_links=[
                SuggestedLink(
                    source_id="x",
                    source_summary="Source",
                    target_id="y",
                    target_summary="Target",
                    reason="Share tags",
                    link_type="tag_shared",
                    confidence=0.8,
                )
            ],
            questions=["Is this correct?"],
            scan_summary="Found 1 issue",
        )

        result = report.to_dict()

        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0]["memory_a_id"] == "a"
        assert result["contradictions"][0]["confidence"] == 0.75
        assert len(result["suggested_links"]) == 1
        assert result["suggested_links"][0]["source_id"] == "x"
        assert result["suggested_links"][0]["link_type"] == "tag_shared"
        assert result["questions"] == ["Is this correct?"]
        assert result["scan_summary"] == "Found 1 issue"
