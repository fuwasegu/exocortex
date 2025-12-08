"""Unit tests for domain services."""

from __future__ import annotations

import pytest

from exocortex.container import Container
from exocortex.domain.exceptions import ValidationError
from exocortex.domain.models import MemoryType, RelationType


class TestMemoryServiceValidation:
    """Tests for MemoryService input validation."""

    def test_empty_content_raises_error(self, container: Container):
        """Test that empty content raises ValidationError."""
        service = container.memory_service

        with pytest.raises(ValidationError) as exc_info:
            service.store_memory(
                content="",
                context_name="test",
                tags=["test"],
            )

        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_content_raises_error(self, container: Container):
        """Test that whitespace-only content raises ValidationError."""
        service = container.memory_service

        with pytest.raises(ValidationError):
            service.store_memory(
                content="   \n\t  ",
                context_name="test",
                tags=["test"],
            )

    def test_empty_context_raises_error(self, container: Container):
        """Test that empty context raises ValidationError."""
        service = container.memory_service

        with pytest.raises(ValidationError) as exc_info:
            service.store_memory(
                content="Valid content",
                context_name="",
                tags=["test"],
            )

        assert "empty" in str(exc_info.value).lower()

    def test_too_many_tags_raises_error(self, container: Container):
        """Test that too many tags raises ValidationError."""
        service = container.memory_service

        # Config has max_tags_per_memory = 20
        tags = [f"tag{i}" for i in range(25)]

        with pytest.raises(ValidationError) as exc_info:
            service.store_memory(
                content="Valid content",
                context_name="test",
                tags=tags,
            )

        assert "too many tags" in str(exc_info.value).lower()


class TestMemoryServiceStore:
    """Tests for MemoryService store operations."""

    def test_store_memory_success(self, container: Container):
        """Test successful memory storage."""
        service = container.memory_service

        result = service.store_memory(
            content="Test insight about Python async patterns.",
            context_name="my-project",
            tags=["python", "async"],
            memory_type=MemoryType.INSIGHT,
        )

        assert result.success is True
        assert result.memory_id is not None
        assert len(result.memory_id) == 36  # UUID format
        assert result.summary is not None

    def test_store_memory_generates_summary(self, container: Container):
        """Test that summary is generated from content."""
        service = container.memory_service

        long_content = "A" * 500  # Longer than max_summary_length

        result = service.store_memory(
            content=long_content,
            context_name="test",
            tags=["test"],
        )

        assert len(result.summary) <= 210  # max_summary_length + "..."
        assert result.summary.endswith("...")

    def test_store_memory_with_all_types(self, container: Container):
        """Test storing memories with all types."""
        service = container.memory_service

        for mem_type in MemoryType:
            result = service.store_memory(
                content=f"Test {mem_type.value} memory",
                context_name="test",
                tags=["test"],
                memory_type=mem_type,
            )

            assert result.success is True

            # Verify type was saved correctly
            memory = service.get_memory(result.memory_id)
            assert memory is not None
            assert memory.memory_type == mem_type


class TestMemoryServiceRecall:
    """Tests for MemoryService recall operations."""

    def test_recall_finds_similar_memories(self, container: Container):
        """Test semantic search finds similar content."""
        service = container.memory_service

        # Store some memories
        service.store_memory(
            content="Python async/await patterns for concurrent programming.",
            context_name="project-a",
            tags=["python", "async"],
        )
        service.store_memory(
            content="JavaScript promises and async functions.",
            context_name="project-b",
            tags=["javascript", "async"],
        )
        service.store_memory(
            content="Database connection pooling strategies.",
            context_name="project-c",
            tags=["database"],
        )

        # Search for async-related content
        memories, total = service.recall_memories(
            query="async programming patterns",
            limit=10,
        )

        assert total > 0
        # First result should be about async
        assert "async" in memories[0].content.lower()

    def test_recall_with_context_filter(self, container: Container):
        """Test filtering by context."""
        service = container.memory_service

        service.store_memory(
            content="Insight from project A",
            context_name="project-a",
            tags=["test"],
        )
        service.store_memory(
            content="Insight from project B",
            context_name="project-b",
            tags=["test"],
        )

        memories, total = service.recall_memories(
            query="insight",
            context_filter="project-a",
        )

        assert total == 1
        assert memories[0].context == "project-a"

    def test_recall_with_tag_filter(self, container: Container):
        """Test filtering by tags."""
        service = container.memory_service

        service.store_memory(
            content="Python best practices",
            context_name="test",
            tags=["python", "best-practice"],
        )
        service.store_memory(
            content="JavaScript best practices",
            context_name="test",
            tags=["javascript", "best-practice"],
        )

        memories, total = service.recall_memories(
            query="best practices",
            tag_filter=["python"],
        )

        assert total == 1
        assert "python" in memories[0].tags


class TestMemoryServiceLink:
    """Tests for MemoryService link operations."""

    def test_link_memories(self, container: Container):
        """Test creating links between memories."""
        service = container.memory_service

        # Create two memories
        result1 = service.store_memory(
            content="Original insight",
            context_name="test",
            tags=["test"],
        )
        result2 = service.store_memory(
            content="Extended insight",
            context_name="test",
            tags=["test"],
        )

        # Link them
        service.link_memories(
            source_id=result2.memory_id,
            target_id=result1.memory_id,
            relation_type=RelationType.EXTENDS,
            reason="Builds on original",
        )

        # Verify link exists
        links = service.get_memory_links(result2.memory_id)
        assert len(links) == 1
        assert links[0].target_id == result1.memory_id
        assert links[0].relation_type == RelationType.EXTENDS

    def test_unlink_memories(self, container: Container):
        """Test removing links."""
        service = container.memory_service

        result1 = service.store_memory(
            content="Memory 1",
            context_name="test",
            tags=["test"],
        )
        result2 = service.store_memory(
            content="Memory 2",
            context_name="test",
            tags=["test"],
        )

        service.link_memories(
            source_id=result2.memory_id,
            target_id=result1.memory_id,
            relation_type=RelationType.RELATED,
        )

        success = service.unlink_memories(result2.memory_id, result1.memory_id)
        assert success is True

        links = service.get_memory_links(result2.memory_id)
        assert len(links) == 0
