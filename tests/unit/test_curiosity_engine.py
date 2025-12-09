"""Unit tests for CuriosityEngine.

Tests for:
- Contradiction detection between memories
- Outdated knowledge detection
- Question generation
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from exocortex.domain.services.curiosity import (
    Contradiction,
    CuriosityEngine,
    CuriosityReport,
    OutdatedKnowledge,
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


class TestCuriosityEngineOutdatedDetection:
    """Tests for outdated knowledge detection."""

    @pytest.fixture
    def engine(self):
        """Create engine with mock repository."""
        mock_repo = MagicMock()
        return CuriosityEngine(repository=mock_repo)

    def test_detects_superseded_memories(self, engine):
        """Memories with supersedes links should be flagged as outdated."""
        # Setup mock
        old_memory = MagicMock()
        old_memory.id = "old-mem"
        old_memory.summary = "Old approach"

        new_memory = MagicMock()
        new_memory.id = "new-mem"
        new_memory.summary = "New approach"

        link = MagicMock()
        link.relation_type = "supersedes"
        link.target_id = "old-mem"

        engine._repo.list_memories.return_value = ([new_memory], 1)
        engine._repo.get_links.return_value = [link]
        engine._repo.get_by_id.return_value = old_memory

        outdated = engine._find_outdated_knowledge(None, 10)

        assert len(outdated) == 1
        assert outdated[0].memory_id == "old-mem"
        assert outdated[0].superseded_by_id == "new-mem"


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
        assert "contradict" in questions[0].lower()

    def test_generates_outdated_question(self, engine):
        """Should generate question when outdated knowledge found."""
        report = CuriosityReport(
            outdated_knowledge=[
                OutdatedKnowledge(
                    memory_id="old",
                    summary="Old stuff",
                    superseded_by_id="new",
                    superseded_by_summary="New stuff",
                    reason="test",
                )
            ]
        )

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        assert "superseded" in questions[0].lower() or "old" in questions[0].lower()

    def test_generates_positive_message_when_clean(self, engine):
        """Should generate positive message when no issues found."""
        report = CuriosityReport()

        questions = engine._generate_questions(report)

        assert len(questions) >= 1
        assert "consistent" in questions[0].lower() or "looks" in questions[0].lower()


class TestCuriosityReportSerialization:
    """Tests for CuriosityReport serialization."""

    def test_to_dict_empty_report(self):
        """Empty report should serialize correctly."""
        report = CuriosityReport()
        result = report.to_dict()

        assert result["contradictions"] == []
        assert result["outdated_knowledge"] == []
        assert result["knowledge_gaps"] == []
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
            questions=["Is this correct?"],
            scan_summary="Found 1 issue",
        )

        result = report.to_dict()

        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0]["memory_a_id"] == "a"
        assert result["contradictions"][0]["confidence"] == 0.75
        assert result["questions"] == ["Is this correct?"]
        assert result["scan_summary"] == "Found 1 issue"
