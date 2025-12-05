"""Integration tests for database layer."""

from __future__ import annotations

import pytest

from exocortex.container import Container
from exocortex.domain.exceptions import DuplicateLinkError, SelfLinkError
from exocortex.domain.models import MemoryType, RelationType


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_database_initialization(self, container: Container):
        """Test that database initializes correctly."""
        db_manager = container.database_manager

        # Execute a simple query to verify connection (use read connection)
        result = db_manager.read_connection.execute("MATCH (n) RETURN count(n)")
        assert result.has_next()

    def test_full_memory_lifecycle(self, container: Container):
        """Test complete memory lifecycle: create, read, update, delete."""
        repo = container.repository

        # Create
        memory_id, summary, _ = repo.create_memory(
            content="Test content for lifecycle",
            context_name="test-project",
            tags=["test", "lifecycle"],
            memory_type=MemoryType.INSIGHT,
        )
        assert memory_id is not None

        # Read
        memory = repo.get_by_id(memory_id)
        assert memory is not None
        assert memory.content == "Test content for lifecycle"
        assert memory.context == "test-project"
        assert set(memory.tags) == {"test", "lifecycle"}

        # Update
        success, changes, new_summary = repo.update_memory(
            memory_id=memory_id,
            content="Updated content",
            tags=["updated"],
        )
        assert success is True
        assert "content" in changes
        assert "tags" in changes

        # Verify update
        memory = repo.get_by_id(memory_id)
        assert memory.content == "Updated content"
        assert memory.tags == ["updated"]

        # Delete
        success = repo.delete_memory(memory_id)
        assert success is True

        # Verify deletion
        memory = repo.get_by_id(memory_id)
        assert memory is None

    def test_memory_relationships(self, container: Container):
        """Test memory-to-memory relationships."""
        repo = container.repository

        # Create two memories
        m1_id, _, _ = repo.create_memory(
            content="Memory 1",
            context_name="test",
            tags=["test"],
            memory_type=MemoryType.INSIGHT,
        )
        m2_id, _, _ = repo.create_memory(
            content="Memory 2",
            context_name="test",
            tags=["test"],
            memory_type=MemoryType.SUCCESS,
        )

        # Create link
        repo.create_link(
            source_id=m2_id,
            target_id=m1_id,
            relation_type=RelationType.EXTENDS,
            reason="M2 extends M1",
        )

        # Verify link exists
        links = repo.get_links(m2_id)
        assert len(links) == 1
        assert links[0].target_id == m1_id
        assert links[0].relation_type == RelationType.EXTENDS

        # Delete link
        success = repo.delete_link(m2_id, m1_id)
        assert success is True

        links = repo.get_links(m2_id)
        assert len(links) == 0

    def test_duplicate_link_prevention(self, container: Container):
        """Test that duplicate links are rejected."""
        repo = container.repository

        m1_id, _, _ = repo.create_memory(
            content="Memory 1",
            context_name="test",
            tags=["test"],
            memory_type=MemoryType.NOTE,
        )
        m2_id, _, _ = repo.create_memory(
            content="Memory 2",
            context_name="test",
            tags=["test"],
            memory_type=MemoryType.NOTE,
        )

        # First link succeeds
        repo.create_link(m2_id, m1_id, RelationType.RELATED)

        # Duplicate link raises error
        with pytest.raises(DuplicateLinkError) as exc_info:
            repo.create_link(m2_id, m1_id, RelationType.EXTENDS)

        assert exc_info.value.existing_type == "related"

    def test_self_link_prevention(self, container: Container):
        """Test that self-links are rejected."""
        repo = container.repository

        m_id, _, _ = repo.create_memory(
            content="Test memory",
            context_name="test",
            tags=["test"],
            memory_type=MemoryType.NOTE,
        )

        with pytest.raises(SelfLinkError):
            repo.create_link(m_id, m_id, RelationType.RELATED)

    def test_semantic_search(self, container: Container):
        """Test semantic search functionality."""
        repo = container.repository

        # Store diverse memories
        repo.create_memory(
            content="Python asyncio for concurrent I/O operations",
            context_name="python-project",
            tags=["python", "async"],
            memory_type=MemoryType.INSIGHT,
        )
        repo.create_memory(
            content="PostgreSQL query optimization techniques",
            context_name="database-project",
            tags=["postgresql", "performance"],
            memory_type=MemoryType.INSIGHT,
        )
        repo.create_memory(
            content="React hooks for state management",
            context_name="frontend-project",
            tags=["react", "hooks"],
            memory_type=MemoryType.INSIGHT,
        )

        # Search for async-related content
        memories, total = repo.search_by_similarity(
            query="asynchronous programming",
            limit=5,
        )

        assert total >= 1
        # Most similar should be the async one
        assert (
            "async" in memories[0].content.lower()
            or "concurrent" in memories[0].content.lower()
        )

    def test_explore_related(self, container: Container):
        """Test exploring related memories."""
        repo = container.repository

        # Create memories with shared tags and context
        m1_id, _, _ = repo.create_memory(
            content="Base insight",
            context_name="shared-project",
            tags=["python", "patterns"],
            memory_type=MemoryType.INSIGHT,
        )
        m2_id, _, _ = repo.create_memory(
            content="Related by tag",
            context_name="other-project",
            tags=["python", "testing"],
            memory_type=MemoryType.INSIGHT,
        )
        m3_id, _, _ = repo.create_memory(
            content="Related by context",
            context_name="shared-project",
            tags=["javascript"],
            memory_type=MemoryType.NOTE,
        )

        # Create direct link
        repo.create_link(m2_id, m1_id, RelationType.EXTENDS)

        result = repo.explore_related(
            memory_id=m1_id,
            include_tag_siblings=True,
            include_context_siblings=True,
        )

        # Should find context sibling
        assert len(result["by_context"]) >= 1

    def test_statistics(self, container: Container):
        """Test statistics gathering."""
        repo = container.repository

        # Create some memories
        for i in range(3):
            repo.create_memory(
                content=f"Insight {i}",
                context_name="test",
                tags=["test"],
                memory_type=MemoryType.INSIGHT,
            )
        repo.create_memory(
            content="Success story",
            context_name="test",
            tags=["test", "success"],
            memory_type=MemoryType.SUCCESS,
        )

        stats = repo.get_stats()

        assert stats.total_memories == 4
        assert stats.memories_by_type.get("insight", 0) == 3
        assert stats.memories_by_type.get("success", 0) == 1
        assert stats.total_contexts >= 1
        assert stats.total_tags >= 2

    def test_analyze_health(self, container: Container):
        """Test knowledge base health analysis."""
        repo = container.repository
        service = container.memory_service

        # Create memories without tags (will trigger orphan warning)
        repo.create_memory(
            content="Orphan memory",
            context_name="test",
            tags=[],  # No tags
            memory_type=MemoryType.NOTE,
        )

        # Use service for health analysis
        result = service.analyze_knowledge()

        assert result.total_memories >= 1
        assert 0 <= result.health_score <= 100
