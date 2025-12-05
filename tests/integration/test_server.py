"""Integration tests for MCP server tools."""

from __future__ import annotations

import pytest

from exocortex.server import (
    analyze_knowledge,
    delete_memory,
    explore_related,
    get_memory,
    get_stats,
    link_memories,
    list_memories,
    ping,
    recall_memories,
    store_memory,
    update_memory,
)


class TestServerTools:
    """Integration tests for MCP server tools."""

    @pytest.fixture(autouse=True)
    def setup(self, container):
        """Reset container before each test."""
        # Container fixture handles setup
        yield
        # Cleanup is handled by container fixture

    def test_ping(self):
        """Test ping tool."""
        result = ping()

        assert result["status"] == "ok"
        assert "operational" in result["message"].lower()

    def test_store_and_recall_memory(self):
        """Test storing and recalling a memory."""
        # Store
        store_result = store_memory(
            content="Python's `asyncio.gather()` runs multiple coroutines concurrently.",
            context_name="python-learning",
            tags=["python", "async", "concurrency"],
            memory_type="insight",
        )

        assert store_result["success"] is True
        assert "memory_id" in store_result
        memory_id = store_result["memory_id"]

        # Recall
        recall_result = recall_memories(
            query="how to run async functions together",
            limit=5,
        )

        assert recall_result["total_found"] >= 1
        # Should find our memory
        found_ids = [m["id"] for m in recall_result["memories"]]
        assert memory_id in found_ids

    def test_store_memory_validation(self):
        """Test store_memory validation."""
        result = store_memory(
            content="",
            context_name="test",
            tags=["test"],
        )

        assert result["success"] is False
        assert "error" in result

    def test_list_memories(self):
        """Test listing memories."""
        # Store a few memories
        for i in range(5):
            store_memory(
                content=f"Test memory {i}",
                context_name="list-test",
                tags=["test"],
            )

        result = list_memories(limit=3, offset=0)

        assert len(result["memories"]) <= 3
        assert result["total_count"] >= 5
        assert "has_more" in result

    def test_get_memory(self):
        """Test getting a specific memory."""
        store_result = store_memory(
            content="Specific memory content",
            context_name="get-test",
            tags=["specific"],
        )
        memory_id = store_result["memory_id"]

        result = get_memory(memory_id)

        assert result["success"] is True
        assert result["memory"]["id"] == memory_id
        assert result["memory"]["content"] == "Specific memory content"

    def test_get_memory_not_found(self):
        """Test getting a non-existent memory."""
        result = get_memory("non-existent-id")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_delete_memory(self):
        """Test deleting a memory."""
        store_result = store_memory(
            content="Memory to delete",
            context_name="delete-test",
            tags=["delete"],
        )
        memory_id = store_result["memory_id"]

        result = delete_memory(memory_id)
        assert result["success"] is True

        # Verify deletion
        get_result = get_memory(memory_id)
        assert get_result["success"] is False

    def test_get_stats(self):
        """Test getting statistics."""
        # Store some memories
        store_memory(
            content="Stats test",
            context_name="stats-test",
            tags=["stats"],
        )

        result = get_stats()

        assert "total_memories" in result
        assert result["total_memories"] >= 1
        assert "memories_by_type" in result
        assert "total_tags" in result

    def test_link_memories(self):
        """Test linking memories."""
        result1 = store_memory(
            content="Original idea",
            context_name="link-test",
            tags=["link"],
        )
        result2 = store_memory(
            content="Building on original",
            context_name="link-test",
            tags=["link"],
        )

        link_result = link_memories(
            source_id=result2["memory_id"],
            target_id=result1["memory_id"],
            relation_type="extends",
            reason="Continuation of thought",
        )

        assert link_result["success"] is True

    def test_link_memories_invalid_type(self):
        """Test linking with invalid relation type."""
        result1 = store_memory(
            content="M1",
            context_name="test",
            tags=["test"],
        )
        result2 = store_memory(
            content="M2",
            context_name="test",
            tags=["test"],
        )

        link_result = link_memories(
            source_id=result2["memory_id"],
            target_id=result1["memory_id"],
            relation_type="invalid_type",
        )

        assert link_result["success"] is False
        assert "invalid" in link_result["error"].lower()

    def test_update_memory(self):
        """Test updating a memory."""
        store_result = store_memory(
            content="Original content",
            context_name="update-test",
            tags=["original"],
        )
        memory_id = store_result["memory_id"]

        update_result = update_memory(
            memory_id=memory_id,
            content="Updated content",
            tags=["updated", "modified"],
        )

        assert update_result["success"] is True
        assert "content" in update_result["changes"]
        assert "tags" in update_result["changes"]

        # Verify update
        get_result = get_memory(memory_id)
        assert get_result["memory"]["content"] == "Updated content"
        assert set(get_result["memory"]["tags"]) == {"updated", "modified"}

    def test_explore_related(self):
        """Test exploring related memories."""
        # Create base memory
        result1 = store_memory(
            content="Base concept",
            context_name="explore-test",
            tags=["base", "concept"],
        )

        # Create related memories
        store_memory(
            content="Same context memory",
            context_name="explore-test",
            tags=["other"],
        )
        store_memory(
            content="Same tag memory",
            context_name="other-context",
            tags=["base"],
        )

        explore_result = explore_related(
            memory_id=result1["memory_id"],
            include_tag_siblings=True,
            include_context_siblings=True,
        )

        assert explore_result["success"] is True
        assert "by_context" in explore_result
        assert "by_tag" in explore_result

    def test_analyze_knowledge(self):
        """Test knowledge analysis."""
        # Store some memories
        store_memory(
            content="Test memory",
            context_name="analyze-test",
            tags=["analyze"],
        )

        result = analyze_knowledge()

        assert "health_score" in result
        assert 0 <= result["health_score"] <= 100
        assert "issues" in result
        assert "suggestions" in result

    def test_knowledge_autonomy_suggestions(self):
        """Test that storing memories generates link suggestions."""
        # Store a base memory
        store_memory(
            content="Database connection pooling is essential for scalable apps.",
            context_name="database-tips",
            tags=["database", "performance", "scaling"],
        )

        # Store a similar memory
        result = store_memory(
            content="Connection pooling with SQLAlchemy improves database performance.",
            context_name="sqlalchemy-project",
            tags=["sqlalchemy", "database", "performance"],
        )

        # Should have suggested links due to similarity
        # (depends on embedding similarity threshold)
        assert "suggested_links" in result
        assert "insights" in result


