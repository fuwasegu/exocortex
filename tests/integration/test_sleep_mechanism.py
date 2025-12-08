"""Integration tests for Sleep/Dream Mechanism (Phase 3).

Tests the deduplication and orphan rescue functionality.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from exocortex.container import Container
from exocortex.domain.models import MemoryType, RelationType


class TestDeduplicationIntegration:
    """Integration tests for duplicate detection and linking."""

    def test_detect_near_duplicate_memories(self, container: Container):
        """Test detection of near-duplicate memories."""
        service = container.memory_service
        repo = container.repository

        # Create two very similar memories
        result1 = service.store_memory(
            content="Always use connection pooling for PostgreSQL database connections to improve performance",
            context_name="project-a",
            tags=["database", "postgresql"],
            memory_type=MemoryType.INSIGHT,
        )

        result2 = service.store_memory(
            content="Use connection pooling for PostgreSQL database connections for better performance",
            context_name="project-b",
            tags=["database", "postgresql"],
            memory_type=MemoryType.INSIGHT,
        )

        # Compute similarity
        mem1 = service.get_memory(result1.memory_id)
        mem2 = service.get_memory(result2.memory_id)

        # Get embeddings
        emb1 = repo._embedding_engine.embed(mem1.content)
        emb2 = repo._embedding_engine.embed(mem2.content)
        similarity = repo.compute_similarity(emb1, emb2)

        # Should be highly similar
        assert similarity > 0.8

    def test_link_duplicates_safely_with_related(self, container: Container):
        """Test that potential duplicates are linked with RELATED for safety.

        Per Gemini3Pro's review: SUPERSEDES is too strong for automatic linking.
        We use RELATED with a clear reason, allowing users to upgrade manually.
        """
        service = container.memory_service

        # Create old memory
        old_result = service.store_memory(
            content="Use index on frequently queried columns",
            context_name="project",
            tags=["database", "performance"],
            memory_type=MemoryType.INSIGHT,
        )

        # Create newer "duplicate"
        new_result = service.store_memory(
            content="Use indexes on frequently queried columns for better query performance",
            context_name="project",
            tags=["database", "performance"],
            memory_type=MemoryType.SUCCESS,
        )

        # Link as RELATED (safer than SUPERSEDES for auto-detection)
        service.link_memories(
            source_id=new_result.memory_id,
            target_id=old_result.memory_id,
            relation_type=RelationType.RELATED,
            reason="⚠️ POTENTIAL_DUPLICATE (similarity: 92%, newer→older). Review and consider 'supersedes'.",
        )

        # Verify link exists with RELATED type
        links = service.get_memory_links(new_result.memory_id)
        assert len(links) == 1
        assert links[0].target_id == old_result.memory_id
        assert links[0].relation_type == RelationType.RELATED
        assert "POTENTIAL_DUPLICATE" in links[0].reason


class TestOrphanRescueIntegration:
    """Integration tests for orphan memory rescue."""

    def test_identify_orphan_memories(self, container: Container):
        """Test identification of orphan memories (no tags, no links)."""
        service = container.memory_service
        repo = container.repository

        # Create a memory with no tags
        result = service.store_memory(
            content="Isolated memory with important content",
            context_name="test-project",
            tags=[],  # No tags - orphan
            memory_type=MemoryType.NOTE,
        )

        # Get orphan memories (returns list of (id, summary) tuples)
        orphans = repo.get_orphan_memories()

        # Should find our orphan
        orphan_ids = [o[0] for o in orphans]  # o is (id, summary) tuple
        assert result.memory_id in orphan_ids

    def test_rescue_orphan_with_related_link(self, container: Container):
        """Test rescuing an orphan by linking to related memory."""
        service = container.memory_service
        repo = container.repository

        # Create a well-connected memory
        connected_result = service.store_memory(
            content="Git workflow: always create feature branches",
            context_name="test-project",
            tags=["git", "workflow"],
            memory_type=MemoryType.INSIGHT,
        )

        # Create an orphan about similar topic
        orphan_result = service.store_memory(
            content="Feature branches help isolate changes",
            context_name="test-project",
            tags=[],  # Orphan
            memory_type=MemoryType.NOTE,
        )

        # Find similar memory for orphan
        orphan = service.get_memory(orphan_result.memory_id)
        embedding = repo._embedding_engine.embed(orphan.content)
        similar = repo.search_similar_by_embedding(
            embedding=embedding,
            limit=3,
            exclude_id=orphan_result.memory_id,
        )

        # Should find the connected memory
        similar_ids = [s[0] for s in similar]
        assert connected_result.memory_id in similar_ids

        # Link orphan to similar
        service.link_memories(
            source_id=orphan_result.memory_id,
            target_id=connected_result.memory_id,
            relation_type=RelationType.RELATED,
            reason="Auto-rescued orphan (test)",
        )

        # Verify link
        links = service.get_memory_links(orphan_result.memory_id)
        assert len(links) == 1


class TestSleepToolIntegration:
    """Integration tests for exo_sleep MCP tool."""

    def test_sleep_tool_spawns_worker(self, container: Container, temp_data_dir: Path):
        """Test that exo_sleep tool can spawn worker process."""
        from exocortex.server import sleep

        # Mock spawn to avoid actually spawning process
        # Use the module where functions are defined, as sleep() does local import
        with patch("exocortex.worker.process.spawn_detached_dreamer") as mock_spawn:
            mock_spawn.return_value = True

            with patch("exocortex.worker.process.is_dreamer_running") as mock_running:
                mock_running.return_value = False

                with patch("exocortex.config.get_config") as mock_config:
                    mock_config.return_value.data_dir = temp_data_dir

                    result = sleep(enable_logging=False)

                    assert result["success"] is True
                    assert result["status"] == "spawned"
                    mock_spawn.assert_called_once()

    def test_sleep_tool_detects_already_running(self, temp_data_dir: Path):
        """Test that exo_sleep detects already running worker."""
        from exocortex.server import sleep

        with patch("exocortex.worker.process.is_dreamer_running") as mock_running:
            mock_running.return_value = True

            with patch("exocortex.config.get_config") as mock_config:
                mock_config.return_value.data_dir = temp_data_dir

                result = sleep()

                assert result["success"] is True
                assert result["status"] == "already_running"

    def test_sleep_tool_handles_spawn_failure(self, temp_data_dir: Path):
        """Test that exo_sleep handles spawn failure gracefully."""
        from exocortex.server import sleep

        with patch("exocortex.worker.process.spawn_detached_dreamer") as mock_spawn:
            mock_spawn.return_value = False

            with patch("exocortex.worker.process.is_dreamer_running") as mock_running:
                mock_running.return_value = False

                with patch("exocortex.config.get_config") as mock_config:
                    mock_config.return_value.data_dir = temp_data_dir

                    result = sleep()

                    assert result["success"] is False
                    assert result["status"] == "failed"


class TestDreamWorkerTasks:
    """Integration tests for DreamWorker task execution."""

    def test_deduplication_task_finds_duplicates(self, container: Container):
        """Test the deduplication task logic."""
        service = container.memory_service
        repo = container.repository

        # Create identical memories
        mem1 = service.store_memory(
            content="Cache invalidation is one of the hardest problems in CS",
            context_name="test",
            tags=["cs", "caching"],
            memory_type=MemoryType.INSIGHT,
        )

        mem2 = service.store_memory(
            content="Cache invalidation is one of the hardest problems in computer science",
            context_name="test",
            tags=["cs", "caching"],
            memory_type=MemoryType.INSIGHT,
        )

        # Simulate deduplication check
        m1 = service.get_memory(mem1.memory_id)
        embedding = repo._embedding_engine.embed(m1.content)

        similar = repo.search_similar_by_embedding(
            embedding=embedding,
            limit=5,
            exclude_id=mem1.memory_id,
        )

        # Should find mem2 with high similarity
        found = False
        for s_id, _, similarity, _, _ in similar:
            if s_id == mem2.memory_id:
                found = True
                assert similarity > 0.85  # Should be very similar
                break

        assert found, "Duplicate memory not found"

    def test_orphan_rescue_task_finds_orphans(self, container: Container):
        """Test the orphan rescue task logic."""
        service = container.memory_service
        repo = container.repository

        # Create orphan
        orphan = service.store_memory(
            content="Orphan memory without any tags",
            context_name="test",
            tags=[],
            memory_type=MemoryType.NOTE,
        )

        # Create non-orphan
        non_orphan = service.store_memory(
            content="Connected memory with tags",
            context_name="test",
            tags=["connected"],
            memory_type=MemoryType.NOTE,
        )

        # Get orphans (returns list of (id, summary) tuples)
        orphans = repo.get_orphan_memories()
        orphan_ids = [o[0] for o in orphans]  # o is (id, summary) tuple

        # Orphan should be found
        assert orphan.memory_id in orphan_ids
        # Non-orphan should not be found
        assert non_orphan.memory_id not in orphan_ids


class TestConsolidationEnd2End:
    """End-to-end tests for the consolidation process."""

    def test_full_consolidation_flow(self, container: Container):
        """Test a complete consolidation scenario."""
        service = container.memory_service
        repo = container.repository

        # Create a cluster of similar memories
        memories = []
        for i in range(4):
            result = service.store_memory(
                content=f"Error handling pattern {i}: always catch specific exceptions and log them",
                context_name="test",
                tags=["error-handling", "best-practice"],
                memory_type=MemoryType.INSIGHT,
            )
            memories.append(result.memory_id)

        # Create an orphan
        orphan = service.store_memory(
            content="Orphan about exception handling best practices",
            context_name="test",
            tags=[],
            memory_type=MemoryType.NOTE,
        )

        # Verify setup (orphans returns list of (id, summary) tuples)
        orphans = repo.get_orphan_memories()
        assert orphan.memory_id in [o[0] for o in orphans]

        # Verify cluster similarity
        m0 = service.get_memory(memories[0])
        embedding = repo._embedding_engine.embed(m0.content)

        similar = repo.search_similar_by_embedding(
            embedding=embedding,
            limit=10,
            exclude_id=memories[0],
        )

        # Should find other cluster members
        similar_ids = [s[0] for s in similar]
        found_cluster = sum(1 for mid in memories[1:] if mid in similar_ids)
        assert found_cluster >= 2, "Should find at least 2 other cluster members"
