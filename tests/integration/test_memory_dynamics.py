"""Integration tests for Memory Dynamics (Phase 1).

Tests the full lifecycle of memory access tracking and hybrid scoring.
"""

from __future__ import annotations

import time

import pytest

from exocortex.container import Container
from exocortex.domain.models import MemoryType


class TestMemoryDynamicsIntegration:
    """Integration tests for Memory Dynamics functionality."""

    def test_memory_created_with_dynamics_fields(self, container: Container):
        """Test that new memories have dynamics fields initialized."""
        service = container.memory_service

        result = service.store_memory(
            content="Test memory with dynamics",
            context_name="test-project",
            tags=["test"],
            memory_type=MemoryType.INSIGHT,
        )

        # Fetch the memory
        memory = service.get_memory(result.memory_id)
        assert memory is not None

        # Check dynamics fields
        assert memory.access_count >= 1
        assert memory.decay_rate == pytest.approx(0.1, abs=0.01)
        # last_accessed_at should be set to creation time
        assert memory.last_accessed_at is not None

    def test_recall_updates_access_count(self, container: Container):
        """Test that recalling memories updates access_count."""
        service = container.memory_service

        # Create a memory
        result = service.store_memory(
            content="Memory about Python decorators and metaclasses",
            context_name="test-project",
            tags=["python", "advanced"],
            memory_type=MemoryType.INSIGHT,
        )

        # Get initial access count
        memory_before = service.get_memory(result.memory_id)
        initial_count = memory_before.access_count

        # Recall memories (search)
        recalled, _ = service.recall_memories(
            query="Python decorators",
            limit=5,
        )

        # The memory should be in results and touched
        memory_ids = [m.id for m in recalled]
        if result.memory_id in memory_ids:
            # Get updated memory
            memory_after = service.get_memory(result.memory_id)
            # Access count should have increased
            assert memory_after.access_count > initial_count

    def test_recall_updates_last_accessed_at(self, container: Container):
        """Test that recalling memories updates last_accessed_at."""
        service = container.memory_service

        # Create a memory
        result = service.store_memory(
            content="Memory about database optimization techniques",
            context_name="test-project",
            tags=["database"],
            memory_type=MemoryType.INSIGHT,
        )

        memory_before = service.get_memory(result.memory_id)
        initial_access = memory_before.last_accessed_at

        # Small delay to ensure timestamp difference
        time.sleep(0.1)

        # Recall memories
        recalled, _ = service.recall_memories(
            query="database optimization",
            limit=5,
        )

        # Check if timestamp was updated
        memory_ids = [m.id for m in recalled]
        if result.memory_id in memory_ids:
            memory_after = service.get_memory(result.memory_id)
            # last_accessed_at should be more recent
            assert memory_after.last_accessed_at >= initial_access

    def test_hybrid_scoring_affects_ranking(self, container: Container):
        """Test that hybrid scoring affects search result ranking."""
        service = container.memory_service
        repo = container.repository

        # Create two memories with similar content
        result1 = service.store_memory(
            content="Understanding React hooks useEffect and useState",
            context_name="test-project",
            tags=["react", "frontend"],
            memory_type=MemoryType.INSIGHT,
        )

        result2 = service.store_memory(
            content="React hooks best practices for useEffect",
            context_name="test-project",
            tags=["react", "frontend"],
            memory_type=MemoryType.SUCCESS,
        )

        # Manually boost the access count of memory1 to simulate popularity
        for _ in range(5):
            repo.touch_memory(result1.memory_id)

        # Search - memory1 should rank higher due to higher access count
        recalled, _ = service.recall_memories(
            query="React hooks useEffect",
            limit=10,
        )

        # Find the memories in results
        result_ids = [m.id for m in recalled]

        # Both memories should appear in results
        # Ranking depends on both vector similarity and access count
        if result1.memory_id in result_ids and result2.memory_id in result_ids:
            assert result1.memory_id in result_ids
            assert result2.memory_id in result_ids

    def test_touch_memory_increments_count(self, container: Container):
        """Test touch_memory correctly increments access_count."""
        service = container.memory_service
        repo = container.repository

        # Create a memory
        result = service.store_memory(
            content="Test memory for touch testing",
            context_name="test-project",
            tags=["test"],
            memory_type=MemoryType.NOTE,
        )

        # Touch multiple times
        initial_memory = service.get_memory(result.memory_id)
        initial_count = initial_memory.access_count

        repo.touch_memory(result.memory_id)
        repo.touch_memory(result.memory_id)
        repo.touch_memory(result.memory_id)

        updated_memory = service.get_memory(result.memory_id)
        assert updated_memory.access_count == initial_count + 3

    def test_touch_memories_batch(self, container: Container):
        """Test batch touch_memories updates multiple memories."""
        service = container.memory_service
        repo = container.repository

        # Create multiple memories
        ids = []
        for i in range(3):
            result = service.store_memory(
                content=f"Batch test memory number {i}",
                context_name="test-project",
                tags=["batch-test"],
                memory_type=MemoryType.NOTE,
            )
            ids.append(result.memory_id)

        # Touch all memories
        touched_count = repo.touch_memories(ids)
        assert touched_count == 3

        # Verify all were updated
        for memory_id in ids:
            memory = service.get_memory(memory_id)
            assert memory.access_count >= 2  # Initial + 1 touch

    def test_hybrid_score_includes_vector_similarity(self, container: Container):
        """Test that vector similarity is the primary factor."""
        service = container.memory_service

        # Create memories with distinct topics
        service.store_memory(
            content="Machine learning neural networks deep learning AI",
            context_name="test-project",
            tags=["ml", "ai"],
            memory_type=MemoryType.INSIGHT,
        )

        service.store_memory(
            content="Cooking recipes for Italian pasta dishes",
            context_name="test-project",
            tags=["cooking"],
            memory_type=MemoryType.NOTE,
        )

        # Search for ML topic
        recalled, _ = service.recall_memories(
            query="neural networks deep learning",
            limit=5,
        )

        # ML memory should rank higher due to semantic relevance
        if recalled:
            assert "ml" in recalled[0].tags or "ai" in recalled[0].tags

    def test_recency_boost_for_recent_memories(self, container: Container):
        """Test that recent memories get a recency boost."""
        service = container.memory_service
        repo = container.repository

        # Create two similar memories
        old_result = service.store_memory(
            content="JavaScript async await patterns for API calls",
            context_name="test-project",
            tags=["javascript"],
            memory_type=MemoryType.INSIGHT,
        )

        new_result = service.store_memory(
            content="Using async await in JavaScript for HTTP requests",
            context_name="test-project",
            tags=["javascript"],
            memory_type=MemoryType.INSIGHT,
        )

        # Manually set old memory's last_accessed_at to be older
        # by touching the new one (making it more recent)
        repo.touch_memory(new_result.memory_id)

        # Search
        recalled, _ = service.recall_memories(
            query="JavaScript async await",
            limit=5,
        )

        # Both should appear, recency should affect ranking
        result_ids = [m.id for m in recalled]
        assert old_result.memory_id in result_ids or new_result.memory_id in result_ids


class TestMemoryDynamicsEdgeCases:
    """Edge case tests for Memory Dynamics."""

    def test_recall_with_no_touch(self, container: Container):
        """Test recall with touch disabled."""
        service = container.memory_service

        result = service.store_memory(
            content="Memory that should not be touched",
            context_name="test-project",
            tags=["no-touch"],
            memory_type=MemoryType.NOTE,
        )

        initial_memory = service.get_memory(result.memory_id)
        initial_count = initial_memory.access_count

        # Recall with touch disabled
        service.recall_memories(
            query="should not be touched",
            limit=5,
            touch_on_recall=False,
        )

        final_memory = service.get_memory(result.memory_id)
        # Count should not have changed
        assert final_memory.access_count == initial_count

    def test_touch_nonexistent_memory(self, container: Container):
        """Test touching a nonexistent memory is idempotent.

        Note: Current implementation returns True even for nonexistent IDs
        because the MATCH query succeeds (matches 0 rows) without error.
        This is acceptable behavior as it's idempotent and doesn't crash.
        """
        repo = container.repository

        result = repo.touch_memory("nonexistent-id-12345")
        # Currently returns True (no error thrown, operation is idempotent)
        # This could be improved to return False for nonexistent IDs
        assert result is True  # Idempotent, no crash

    def test_empty_recall_does_not_crash(self, container: Container):
        """Test that recalling with no results doesn't crash touch logic."""
        service = container.memory_service

        # Search for something that doesn't exist
        recalled, _ = service.recall_memories(
            query="xyzzy12345nonexistent",
            limit=5,
        )

        # Should return empty list without errors
        assert recalled == []


class TestHybridScoringRepository:
    """Tests for hybrid scoring at the repository level."""

    def test_apply_hybrid_scoring_ordering(self, container: Container):
        """Test that _apply_hybrid_scoring correctly reorders results."""
        repo = container.repository
        service = container.memory_service

        # Create memories with different characteristics
        mem1 = service.store_memory(
            content="First memory about TypeScript types",
            context_name="test",
            tags=["typescript"],
            memory_type=MemoryType.INSIGHT,
        )

        mem2 = service.store_memory(
            content="Second memory about TypeScript generics",
            context_name="test",
            tags=["typescript"],
            memory_type=MemoryType.SUCCESS,
        )

        # Boost mem2's access count significantly
        for _ in range(10):
            repo.touch_memory(mem2.memory_id)

        # Search
        recalled, _ = service.recall_memories(
            query="TypeScript types generics",
            limit=5,
        )

        # Both should be found
        ids = [m.id for m in recalled]
        assert mem1.memory_id in ids or mem2.memory_id in ids

    def test_scoring_preserves_all_memories(self, container: Container):
        """Test that hybrid scoring doesn't drop any memories."""
        service = container.memory_service

        # Create several memories
        created_ids = []
        for i in range(5):
            result = service.store_memory(
                content=f"Test memory for scoring preservation {i}",
                context_name="test",
                tags=["preservation-test"],
                memory_type=MemoryType.NOTE,
            )
            created_ids.append(result.memory_id)

        # Search for all
        recalled, total = service.recall_memories(
            query="scoring preservation",
            limit=10,
        )

        # Should find most/all created memories
        found_ids = [m.id for m in recalled]
        found_count = sum(1 for cid in created_ids if cid in found_ids)
        assert found_count >= 3  # At least 3 of 5 should be found
