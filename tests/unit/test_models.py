"""Unit tests for domain models."""

from __future__ import annotations

from datetime import datetime, timezone

from exocortex.domain.models import (
    KnowledgeInsight,
    Memory,
    MemoryType,
    MemoryWithContext,
    RelationType,
    StoreMemoryResult,
    SuggestedLink,
)


class TestMemory:
    """Tests for Memory model."""

    def test_create_memory(self):
        """Test creating a basic memory."""
        now = datetime.now(timezone.utc)
        memory = Memory(
            id="test-123",
            content="Test content",
            summary="Test summary",
            memory_type=MemoryType.INSIGHT,
            created_at=now,
            updated_at=now,
        )

        assert memory.id == "test-123"
        assert memory.content == "Test content"
        assert memory.summary == "Test summary"
        assert memory.memory_type == MemoryType.INSIGHT
        assert memory.created_at == now
        assert memory.updated_at == now

    def test_memory_types(self):
        """Test all memory types."""
        assert MemoryType.INSIGHT.value == "insight"
        assert MemoryType.SUCCESS.value == "success"
        assert MemoryType.FAILURE.value == "failure"
        assert MemoryType.DECISION.value == "decision"
        assert MemoryType.NOTE.value == "note"


class TestMemoryWithContext:
    """Tests for MemoryWithContext model."""

    def test_create_with_context(self):
        """Test creating memory with context and tags."""
        now = datetime.now(timezone.utc)
        memory = MemoryWithContext(
            id="test-456",
            content="Content with context",
            summary="Summary",
            memory_type=MemoryType.SUCCESS,
            created_at=now,
            updated_at=now,
            context="my-project",
            tags=["python", "database"],
            similarity=0.95,
        )

        assert memory.context == "my-project"
        assert memory.tags == ["python", "database"]
        assert memory.similarity == 0.95

    def test_default_values(self):
        """Test default values for optional fields."""
        now = datetime.now(timezone.utc)
        memory = MemoryWithContext(
            id="test-789",
            content="Minimal content",
            summary="Summary",
            memory_type=MemoryType.NOTE,
            created_at=now,
            updated_at=now,
        )

        assert memory.context is None
        assert memory.tags == []
        assert memory.similarity is None
        assert memory.related_memories == []


class TestRelationType:
    """Tests for RelationType enum."""

    def test_relation_types(self):
        """Test all relation types."""
        assert RelationType.RELATED.value == "related"
        assert RelationType.SUPERSEDES.value == "supersedes"
        assert RelationType.CONTRADICTS.value == "contradicts"
        assert RelationType.EXTENDS.value == "extends"
        assert RelationType.DEPENDS_ON.value == "depends_on"


class TestSuggestedLink:
    """Tests for SuggestedLink model."""

    def test_create_suggested_link(self):
        """Test creating a suggested link."""
        link = SuggestedLink(
            target_id="target-123",
            target_summary="Target summary",
            similarity=0.85,
            suggested_relation=RelationType.EXTENDS,
            reason="High semantic similarity",
        )

        assert link.target_id == "target-123"
        assert link.similarity == 0.85
        assert link.suggested_relation == RelationType.EXTENDS


class TestKnowledgeInsight:
    """Tests for KnowledgeInsight model."""

    def test_create_insight(self):
        """Test creating a knowledge insight."""
        insight = KnowledgeInsight(
            insight_type="potential_duplicate",
            message="Very similar memory exists",
            related_memory_id="other-123",
            related_memory_summary="Other summary",
            confidence=0.92,
            suggested_action="Consider using update_memory",
        )

        assert insight.insight_type == "potential_duplicate"
        assert insight.confidence == 0.92
        assert insight.related_memory_id == "other-123"


class TestStoreMemoryResult:
    """Tests for StoreMemoryResult model."""

    def test_create_result(self):
        """Test creating a store memory result."""
        result = StoreMemoryResult(
            success=True,
            memory_id="new-123",
            summary="New memory summary",
            suggested_links=[],
            insights=[],
        )

        assert result.success is True
        assert result.memory_id == "new-123"
        assert result.suggested_links == []
        assert result.insights == []

    def test_result_with_suggestions(self):
        """Test result with suggested links and insights."""
        link = SuggestedLink(
            target_id="target-456",
            target_summary="Target",
            similarity=0.80,
            suggested_relation=RelationType.RELATED,
            reason="Similar topic",
        )

        insight = KnowledgeInsight(
            insight_type="success_after_failure",
            message="This may resolve a previous failure",
            related_memory_id="failure-789",
            related_memory_summary="Failed attempt",
            confidence=0.75,
            suggested_action="Link with extends relation",
        )

        result = StoreMemoryResult(
            success=True,
            memory_id="new-456",
            summary="Summary",
            suggested_links=[link],
            insights=[insight],
        )

        assert len(result.suggested_links) == 1
        assert len(result.insights) == 1
        assert result.suggested_links[0].target_id == "target-456"
        assert result.insights[0].insight_type == "success_after_failure"


