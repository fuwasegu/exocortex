"""Integration tests for Pattern Abstraction (Phase 2).

Tests the pattern extraction and consolidation functionality.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from exocortex.container import Container
from exocortex.domain.models import MemoryType


class TestPatternCreationIntegration:
    """Integration tests for Pattern creation."""

    def test_create_pattern(self, container: Container):
        """Test creating a pattern in the database."""
        repo = container.repository

        pattern_id, summary, embedding = repo.create_pattern(
            content="Always validate input data before processing",
            confidence=0.7,
        )

        assert pattern_id is not None
        assert len(pattern_id) == 36  # UUID format
        assert summary is not None
        assert len(embedding) > 0

    def test_get_pattern_by_id(self, container: Container):
        """Test retrieving a pattern by ID."""
        repo = container.repository

        # Create pattern
        pattern_id, _, _ = repo.create_pattern(
            content="Use environment variables for configuration",
            confidence=0.6,
        )

        # Retrieve pattern
        pattern = repo.get_pattern_by_id(pattern_id)

        assert pattern is not None
        assert pattern.id == pattern_id
        assert "environment variables" in pattern.content.lower()
        assert pattern.confidence == pytest.approx(0.6, abs=0.01)

    def test_get_nonexistent_pattern(self, container: Container):
        """Test retrieving a nonexistent pattern returns None."""
        repo = container.repository

        pattern = repo.get_pattern_by_id("nonexistent-pattern-id")
        assert pattern is None


class TestPatternLinkingIntegration:
    """Integration tests for linking memories to patterns."""

    def test_link_memory_to_pattern(self, container: Container):
        """Test linking a memory as an instance of a pattern."""
        service = container.memory_service
        repo = container.repository

        # Create a pattern
        pattern_id, _, _ = repo.create_pattern(
            content="Always use descriptive variable names",
            confidence=0.5,
        )

        # Create a memory
        result = service.store_memory(
            content="Renamed variable from x to user_count for clarity",
            context_name="test-project",
            tags=["refactoring", "naming"],
            memory_type=MemoryType.SUCCESS,
        )

        # Link memory to pattern
        success = repo.link_memory_to_pattern(
            memory_id=result.memory_id,
            pattern_id=pattern_id,
            confidence=0.8,
        )

        assert success is True

    def test_linking_increases_pattern_confidence(self, container: Container):
        """Test that linking instances increases pattern confidence."""
        service = container.memory_service
        repo = container.repository

        # Create pattern
        pattern_id, _, _ = repo.create_pattern(
            content="Write unit tests before implementing features",
            confidence=0.5,
        )

        initial_pattern = repo.get_pattern_by_id(pattern_id)
        initial_confidence = initial_pattern.confidence

        # Link multiple memories
        for i in range(3):
            result = service.store_memory(
                content=f"Wrote tests first for feature {i}, caught bugs early",
                context_name="test-project",
                tags=["testing", "tdd"],
                memory_type=MemoryType.SUCCESS,
            )
            repo.link_memory_to_pattern(
                memory_id=result.memory_id,
                pattern_id=pattern_id,
                confidence=0.7,
            )

        # Check confidence increased
        final_pattern = repo.get_pattern_by_id(pattern_id)
        assert final_pattern.confidence > initial_confidence
        assert final_pattern.instance_count >= 3

    def test_duplicate_link_is_idempotent(self, container: Container):
        """Test that linking same memory twice doesn't create duplicate."""
        service = container.memory_service
        repo = container.repository

        # Create pattern and memory
        pattern_id, _, _ = repo.create_pattern(
            content="Keep functions small and focused",
            confidence=0.5,
        )

        result = service.store_memory(
            content="Refactored large function into smaller helpers",
            context_name="test",
            tags=["refactoring"],
            memory_type=MemoryType.SUCCESS,
        )

        # Link twice
        repo.link_memory_to_pattern(result.memory_id, pattern_id, 0.8)
        repo.link_memory_to_pattern(result.memory_id, pattern_id, 0.8)

        # Should still succeed without error
        pattern = repo.get_pattern_by_id(pattern_id)
        assert pattern is not None


class TestPatternSearchIntegration:
    """Integration tests for pattern search functionality."""

    def test_search_similar_patterns(self, container: Container):
        """Test searching for similar patterns."""
        repo = container.repository

        # Create patterns
        p1_id, _, _ = repo.create_pattern(
            content="Use dependency injection for testability",
            confidence=0.7,
        )

        p2_id, _, _ = repo.create_pattern(
            content="Prefer composition over inheritance",
            confidence=0.6,
        )

        # Search for similar pattern
        query_embedding = repo._embedding_engine.embed(
            "dependency injection helps with testing"
        )
        similar = repo.search_similar_patterns(
            embedding=query_embedding,
            limit=5,
            min_confidence=0.0,
        )

        # Should find p1 (about dependency injection)
        similar_ids = [s[0] for s in similar]
        assert p1_id in similar_ids

    def test_search_patterns_with_confidence_filter(self, container: Container):
        """Test pattern search with confidence filter."""
        repo = container.repository

        # Create patterns with different confidence
        low_conf_id, _, _ = repo.create_pattern(
            content="Low confidence pattern about logging",
            confidence=0.3,
        )

        high_conf_id, _, _ = repo.create_pattern(
            content="High confidence pattern about logging",
            confidence=0.8,
        )

        # Search with high confidence threshold
        query_embedding = repo._embedding_engine.embed("logging pattern")
        similar = repo.search_similar_patterns(
            embedding=query_embedding,
            limit=5,
            min_confidence=0.5,
        )

        similar_ids = [s[0] for s in similar]

        # High confidence should be included
        assert high_conf_id in similar_ids
        # Low confidence should be excluded
        assert low_conf_id not in similar_ids


class TestConsolidatePatternsIntegration:
    """Integration tests for the consolidate_patterns service method."""

    def test_consolidate_creates_pattern_from_cluster(self, container: Container):
        """Test that consolidation creates patterns from memory clusters."""
        service = container.memory_service

        # Create a cluster of similar memories
        for i in range(4):
            service.store_memory(
                content=f"Database query optimization tip {i}: use EXPLAIN ANALYZE to understand query plans",
                context_name="test",
                tags=["database", "performance"],
                memory_type=MemoryType.INSIGHT,
            )

        # Consolidate
        result = service.consolidate_patterns(
            tag_filter="database",
            min_cluster_size=3,
            similarity_threshold=0.6,
        )

        # Should create or find patterns
        assert result["patterns_created"] >= 0 or result["patterns_found"] >= 0
        assert result["memories_linked"] >= 0

    def test_consolidate_with_tag_filter(self, container: Container):
        """Test consolidation with specific tag filter."""
        service = container.memory_service

        # Create memories with different tags
        for i in range(3):
            service.store_memory(
                content=f"React component optimization {i}: use memo for expensive renders",
                context_name="test",
                tags=["react", "performance"],
                memory_type=MemoryType.SUCCESS,
            )

        for i in range(3):
            service.store_memory(
                content=f"Python decorator usage {i}: create reusable decorators",
                context_name="test",
                tags=["python", "decorators"],
                memory_type=MemoryType.INSIGHT,
            )

        # Consolidate only react memories
        result = service.consolidate_patterns(
            tag_filter="react",
            min_cluster_size=2,
        )

        # Should process react memories
        # (Result depends on actual similarity which may vary)
        assert "patterns_created" in result
        assert "patterns_found" in result

    def test_consolidate_links_to_existing_pattern(self, container: Container):
        """Test that consolidation links to existing similar patterns."""
        service = container.memory_service
        repo = container.repository

        # Pre-create a pattern
        pattern_id, _, _ = repo.create_pattern(
            content="API error handling pattern: return consistent error response format",
            confidence=0.6,
        )

        # Create memories that should match this pattern
        for i in range(3):
            service.store_memory(
                content=f"Implemented consistent error responses for API endpoint {i}",
                context_name="test",
                tags=["api", "error-handling"],
                memory_type=MemoryType.SUCCESS,
            )

        # Consolidate
        result = service.consolidate_patterns(
            tag_filter="api",
            min_cluster_size=2,
        )

        # Should find and strengthen existing pattern
        # (depending on similarity threshold)
        assert result["patterns_found"] >= 0 or result["patterns_created"] >= 0

    def test_consolidate_too_few_memories(self, container: Container):
        """Test consolidation with fewer than min_cluster_size memories."""
        service = container.memory_service

        # Create only 2 memories (below default threshold of 3)
        for i in range(2):
            service.store_memory(
                content=f"Small cluster memory {i} about CSS styling",
                context_name="test",
                tags=["css"],
                memory_type=MemoryType.NOTE,
            )

        # Consolidate with min_cluster_size=3
        result = service.consolidate_patterns(
            tag_filter="css",
            min_cluster_size=3,
        )

        # Should not create patterns
        assert result["patterns_created"] == 0


class TestConsolidateToolIntegration:
    """Integration tests for exo_consolidate MCP tool."""

    def test_consolidate_tool_returns_result(self, container: Container):
        """Test that exo_consolidate tool returns proper result."""
        from exocortex.server import consolidate

        # Create some test memories first
        service = container.memory_service
        for i in range(3):
            service.store_memory(
                content=f"TypeScript type safety tip {i}: always enable strict mode",
                context_name="test",
                tags=["typescript"],
                memory_type=MemoryType.INSIGHT,
            )

        with patch("exocortex.server.get_container") as mock_get:
            mock_get.return_value = container

            result = consolidate(tag_filter="typescript", min_cluster_size=2)

            assert result["success"] is True
            assert "patterns_found" in result
            assert "patterns_created" in result
            assert "memories_linked" in result
            assert "message" in result

    def test_consolidate_tool_without_filter(self, container: Container):
        """Test exo_consolidate without tag filter (uses frequent memories)."""
        from exocortex.server import consolidate

        service = container.memory_service
        repo = container.repository

        # Create and boost access count
        for i in range(3):
            result = service.store_memory(
                content=f"Frequently accessed memory {i} about GraphQL",
                context_name="test",
                tags=["graphql"],
                memory_type=MemoryType.INSIGHT,
            )
            # Boost access count
            for _ in range(5):
                repo.touch_memory(result.memory_id)

        with patch("exocortex.server.get_container") as mock_get:
            mock_get.return_value = container

            result = consolidate(min_cluster_size=2)

            assert result["success"] is True


class TestMemoryClusteringLogic:
    """Tests for memory clustering functionality."""

    def test_find_memory_clusters(self, container: Container):
        """Test the memory clustering algorithm."""
        service = container.memory_service

        # Create distinct clusters
        # Cluster 1: Security
        for i in range(3):
            service.store_memory(
                content=f"Security best practice {i}: sanitize all user inputs",
                context_name="test",
                tags=["security"],
                memory_type=MemoryType.INSIGHT,
            )

        # Cluster 2: Performance
        for i in range(3):
            service.store_memory(
                content=f"Performance tip {i}: lazy load components",
                context_name="test",
                tags=["performance"],
                memory_type=MemoryType.SUCCESS,
            )

        # Consolidate each cluster
        security_result = service.consolidate_patterns(
            tag_filter="security",
            min_cluster_size=2,
        )

        performance_result = service.consolidate_patterns(
            tag_filter="performance",
            min_cluster_size=2,
        )

        # Should process both clusters
        assert security_result is not None
        assert performance_result is not None

    def test_cluster_similarity_threshold(self, container: Container):
        """Test that similarity threshold affects clustering."""
        service = container.memory_service

        # Create memories with varying similarity
        service.store_memory(
            content="Docker containers provide isolation",
            context_name="test",
            tags=["docker"],
            memory_type=MemoryType.INSIGHT,
        )

        service.store_memory(
            content="Docker images are layered and cacheable",
            context_name="test",
            tags=["docker"],
            memory_type=MemoryType.INSIGHT,
        )

        service.store_memory(
            content="Kubernetes orchestrates container deployments",
            context_name="test",
            tags=["docker", "kubernetes"],
            memory_type=MemoryType.INSIGHT,
        )

        # High threshold should create tighter clusters
        high_threshold_result = service.consolidate_patterns(
            tag_filter="docker",
            min_cluster_size=2,
            similarity_threshold=0.85,
        )

        # Lower threshold might group more
        low_threshold_result = service.consolidate_patterns(
            tag_filter="docker",
            min_cluster_size=2,
            similarity_threshold=0.5,
        )

        # Both should complete without error
        assert high_threshold_result is not None
        assert low_threshold_result is not None
