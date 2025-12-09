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


class TestTraceLineage:
    """Integration tests for trace_lineage (Temporal Reasoning)."""

    def test_trace_lineage_backward(self, container: Container):
        """Test tracing lineage backward to find ancestors."""
        repo = container.repository

        # Create a chain: m3 -> m2 -> m1 (evolved_from)
        m1_id, _, _ = repo.create_memory(
            content="Original decision",
            context_name="test",
            tags=["decision"],
            memory_type=MemoryType.DECISION,
        )
        m2_id, _, _ = repo.create_memory(
            content="Evolved decision v2",
            context_name="test",
            tags=["decision"],
            memory_type=MemoryType.DECISION,
        )
        m3_id, _, _ = repo.create_memory(
            content="Final decision v3",
            context_name="test",
            tags=["decision"],
            memory_type=MemoryType.DECISION,
        )

        # Create links: m3 evolved_from m2, m2 evolved_from m1
        repo.create_link(m2_id, m1_id, RelationType.EVOLVED_FROM, "v2 evolved from v1")
        repo.create_link(m3_id, m2_id, RelationType.EVOLVED_FROM, "v3 evolved from v2")

        # Trace backward from m3
        lineage = repo.trace_lineage(
            memory_id=m3_id,
            direction="backward",
            relation_types=["evolved_from"],
        )

        assert len(lineage) == 2
        # Should find m2 at depth 1, m1 at depth 2
        lineage_ids = [node["id"] for node in lineage]
        assert m2_id in lineage_ids
        assert m1_id in lineage_ids

    def test_trace_lineage_forward(self, container: Container):
        """Test tracing lineage forward to find descendants."""
        repo = container.repository

        # Create a chain: m1 <- m2 <- m3 (evolved_from)
        m1_id, _, _ = repo.create_memory(
            content="Root insight",
            context_name="test",
            tags=["insight"],
            memory_type=MemoryType.INSIGHT,
        )
        m2_id, _, _ = repo.create_memory(
            content="Child insight",
            context_name="test",
            tags=["insight"],
            memory_type=MemoryType.INSIGHT,
        )
        m3_id, _, _ = repo.create_memory(
            content="Grandchild insight",
            context_name="test",
            tags=["insight"],
            memory_type=MemoryType.INSIGHT,
        )

        # Create links
        repo.create_link(m2_id, m1_id, RelationType.EVOLVED_FROM)
        repo.create_link(m3_id, m2_id, RelationType.EVOLVED_FROM)

        # Trace forward from m1 (find what evolved FROM this)
        lineage = repo.trace_lineage(
            memory_id=m1_id,
            direction="forward",
            relation_types=["evolved_from"],
        )

        assert len(lineage) == 2
        lineage_ids = [node["id"] for node in lineage]
        assert m2_id in lineage_ids
        assert m3_id in lineage_ids

    def test_trace_lineage_with_multiple_relation_types(self, container: Container):
        """Test tracing with multiple relation types."""
        repo = container.repository

        # Create memories
        m1_id, _, _ = repo.create_memory(
            content="Original approach",
            context_name="test",
            tags=["approach"],
            memory_type=MemoryType.DECISION,
        )
        m2_id, _, _ = repo.create_memory(
            content="Bug caused by original",
            context_name="test",
            tags=["bug"],
            memory_type=MemoryType.FAILURE,
        )
        m3_id, _, _ = repo.create_memory(
            content="Rejected due to bug",
            context_name="test",
            tags=["rejected"],
            memory_type=MemoryType.DECISION,
        )

        # m2 was caused_by m1, m3 was rejected_because of m2
        repo.create_link(m2_id, m1_id, RelationType.CAUSED_BY, "Bug caused by decision")
        repo.create_link(
            m3_id, m2_id, RelationType.REJECTED_BECAUSE, "Rejected due to bug"
        )

        # Trace with both relation types
        lineage = repo.trace_lineage(
            memory_id=m3_id,
            direction="backward",
            relation_types=["caused_by", "rejected_because"],
        )

        assert len(lineage) == 2

    def test_trace_lineage_respects_max_depth(self, container: Container):
        """Test that max_depth limits traversal."""
        repo = container.repository

        # Create a long chain: m5 -> m4 -> m3 -> m2 -> m1
        memory_ids = []
        for i in range(5):
            m_id, _, _ = repo.create_memory(
                content=f"Memory {i}",
                context_name="test",
                tags=["chain"],
                memory_type=MemoryType.NOTE,
            )
            memory_ids.append(m_id)

        # Link them: each evolved from the previous
        for i in range(1, 5):
            repo.create_link(
                memory_ids[i], memory_ids[i - 1], RelationType.EVOLVED_FROM
            )

        # Trace with max_depth=2 from the last one
        lineage = repo.trace_lineage(
            memory_id=memory_ids[4],
            direction="backward",
            relation_types=["evolved_from"],
            max_depth=2,
        )

        # Should only find 2 levels (m3, m2), not m1, m0
        assert len(lineage) == 2
        assert all(node["depth"] <= 2 for node in lineage)

    def test_trace_lineage_empty_when_no_links(self, container: Container):
        """Test that trace returns empty list when no links exist."""
        repo = container.repository

        m_id, _, _ = repo.create_memory(
            content="Isolated memory",
            context_name="test",
            tags=["isolated"],
            memory_type=MemoryType.NOTE,
        )

        lineage = repo.trace_lineage(memory_id=m_id, direction="backward")

        assert lineage == []
