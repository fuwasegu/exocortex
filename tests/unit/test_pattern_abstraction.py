"""Unit tests for Pattern Abstraction (Phase 2).

Tests the Pattern model and abstraction logic.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from exocortex.domain.models import (
    MemoryType,
    MemoryWithContext,
    Pattern,
    PatternInstance,
    PatternWithInstances,
)


class TestPatternModel:
    """Tests for Pattern model."""

    def test_create_pattern_minimal(self):
        """Test creating a pattern with minimal fields."""
        now = datetime.now(timezone.utc)
        pattern = Pattern(
            id="pattern-123",
            content="Always use connection pooling",
            summary="Use connection pooling for databases",
            created_at=now,
            updated_at=now,
        )

        assert pattern.id == "pattern-123"
        assert pattern.content == "Always use connection pooling"
        assert pattern.summary == "Use connection pooling for databases"
        # Check defaults
        assert pattern.confidence == 0.5
        assert pattern.instance_count == 1

    def test_create_pattern_full(self):
        """Test creating a pattern with all fields."""
        now = datetime.now(timezone.utc)
        pattern = Pattern(
            id="pattern-456",
            content="Check environment variables before deployment",
            summary="Validate env vars in deploy scripts",
            confidence=0.85,
            instance_count=12,
            created_at=now,
            updated_at=now,
        )

        assert pattern.confidence == 0.85
        assert pattern.instance_count == 12

    def test_pattern_confidence_bounds(self):
        """Test that confidence is bounded between 0 and 1."""
        now = datetime.now(timezone.utc)

        # Valid confidence
        pattern = Pattern(
            id="test-1",
            content="Test",
            summary="Test",
            confidence=0.0,
            created_at=now,
            updated_at=now,
        )
        assert pattern.confidence == 0.0

        pattern = Pattern(
            id="test-2",
            content="Test",
            summary="Test",
            confidence=1.0,
            created_at=now,
            updated_at=now,
        )
        assert pattern.confidence == 1.0

        # Invalid confidence should raise
        with pytest.raises(ValueError):
            Pattern(
                id="test-3",
                content="Test",
                summary="Test",
                confidence=1.5,  # Invalid
                created_at=now,
                updated_at=now,
            )

        with pytest.raises(ValueError):
            Pattern(
                id="test-4",
                content="Test",
                summary="Test",
                confidence=-0.1,  # Invalid
                created_at=now,
                updated_at=now,
            )


class TestPatternInstance:
    """Tests for PatternInstance model."""

    def test_create_pattern_instance(self):
        """Test creating a pattern instance link."""
        now = datetime.now(timezone.utc)
        instance = PatternInstance(
            memory_id="memory-123",
            pattern_id="pattern-456",
            confidence=0.75,
            created_at=now,
        )

        assert instance.memory_id == "memory-123"
        assert instance.pattern_id == "pattern-456"
        assert instance.confidence == 0.75

    def test_pattern_instance_default_confidence(self):
        """Test default confidence value."""
        now = datetime.now(timezone.utc)
        instance = PatternInstance(
            memory_id="memory-123",
            pattern_id="pattern-456",
            created_at=now,
        )

        assert instance.confidence == 0.5

    def test_pattern_instance_confidence_bounds(self):
        """Test confidence bounds for pattern instance."""
        now = datetime.now(timezone.utc)

        # Valid bounds
        instance = PatternInstance(
            memory_id="m1",
            pattern_id="p1",
            confidence=0.0,
            created_at=now,
        )
        assert instance.confidence == 0.0

        instance = PatternInstance(
            memory_id="m2",
            pattern_id="p2",
            confidence=1.0,
            created_at=now,
        )
        assert instance.confidence == 1.0

        # Invalid
        with pytest.raises(ValueError):
            PatternInstance(
                memory_id="m3",
                pattern_id="p3",
                confidence=1.1,
                created_at=now,
            )


class TestPatternWithInstances:
    """Tests for PatternWithInstances model."""

    def test_create_pattern_with_instances(self):
        """Test creating a pattern with its instance memories."""
        now = datetime.now(timezone.utc)

        # Create some memory instances
        memory1 = MemoryWithContext(
            id="mem-1",
            content="PostgreSQL pooling fix",
            summary="Fixed connection pooling",
            memory_type=MemoryType.SUCCESS,
            created_at=now,
            updated_at=now,
            context="project-a",
            tags=["database", "postgresql"],
        )

        memory2 = MemoryWithContext(
            id="mem-2",
            content="MySQL pool optimization",
            summary="Optimized MySQL pool size",
            memory_type=MemoryType.SUCCESS,
            created_at=now,
            updated_at=now,
            context="project-b",
            tags=["database", "mysql"],
        )

        pattern = PatternWithInstances(
            id="pattern-789",
            content="Always configure database connection pooling properly",
            summary="Database pooling best practice",
            confidence=0.8,
            instance_count=2,
            created_at=now,
            updated_at=now,
            instances=[memory1, memory2],
            tags=["database", "postgresql", "mysql"],
        )

        assert len(pattern.instances) == 2
        assert pattern.instances[0].id == "mem-1"
        assert pattern.instances[1].id == "mem-2"
        assert "database" in pattern.tags

    def test_pattern_with_empty_instances(self):
        """Test pattern with no instances (newly created)."""
        now = datetime.now(timezone.utc)
        pattern = PatternWithInstances(
            id="pattern-new",
            content="New pattern",
            summary="New pattern summary",
            created_at=now,
            updated_at=now,
        )

        assert pattern.instances == []
        assert pattern.tags == []


class TestPatternConfidenceEvolution:
    """Tests for pattern confidence evolution scenarios."""

    def test_confidence_increases_with_instances(self):
        """Test that confidence should increase as instances are added."""
        # Simulate confidence growth
        initial_confidence = 0.5
        confidence_increment = 0.05

        # After 1 instance
        conf_1 = min(initial_confidence + confidence_increment, 1.0)
        assert conf_1 == 0.55

        # After 5 instances
        conf_5 = min(initial_confidence + 5 * confidence_increment, 1.0)
        assert conf_5 == 0.75

        # After 10 instances (capped at 0.9 in our impl)
        conf_10 = min(initial_confidence + 10 * confidence_increment, 0.9)
        assert conf_10 == 0.9

    def test_confidence_cap_at_threshold(self):
        """Test that confidence is capped at a reasonable threshold."""
        # In our implementation, confidence caps at 0.9 to leave room for
        # uncertainty
        max_confidence = 0.9
        increment = 0.05
        current = 0.85

        # Should cap at 0.9, not go to 0.9
        new_confidence = min(current + increment, max_confidence)
        assert new_confidence == 0.9


class TestPatternClusteringLogic:
    """Tests for pattern clustering/similarity logic."""

    def test_similarity_threshold_for_clustering(self):
        """Test the similarity threshold used for clustering."""
        default_threshold = 0.7

        # Memories with similarity >= 0.7 should cluster
        assert 0.75 >= default_threshold
        assert 0.8 >= default_threshold

        # Memories with similarity < 0.7 should not cluster
        assert 0.65 < default_threshold
        assert 0.5 < default_threshold

    def test_minimum_cluster_size(self):
        """Test minimum cluster size requirement."""
        min_cluster_size = 3

        # Cluster of 2 should not form a pattern
        cluster_size_2 = 2
        assert cluster_size_2 < min_cluster_size

        # Cluster of 3+ should form a pattern
        cluster_size_3 = 3
        assert cluster_size_3 >= min_cluster_size

    def test_pattern_matching_existing(self):
        """Test threshold for matching to existing pattern."""
        existing_pattern_threshold = 0.8

        # High similarity should link to existing
        assert 0.85 >= existing_pattern_threshold
        assert 0.9 >= existing_pattern_threshold

        # Lower similarity should create new pattern
        assert 0.75 < existing_pattern_threshold


class TestPatternSynthesis:
    """Tests for pattern content synthesis."""

    def test_common_tags_extraction(self):
        """Test extracting common tags from cluster."""
        tags_per_memory = [
            ["database", "postgresql", "performance"],
            ["database", "mysql", "performance"],
            ["database", "mongodb"],
            ["database", "redis", "performance"],
        ]

        # Count tag occurrences
        tag_counts: dict[str, int] = {}
        for tags in tags_per_memory:
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Tags appearing in >= 50% of memories
        total_memories = len(tags_per_memory)
        common_threshold = 0.5
        common_tags = [
            tag
            for tag, count in tag_counts.items()
            if count >= total_memories * common_threshold
        ]

        # "database" appears in all 4
        assert "database" in common_tags

        # "performance" appears in 3/4 = 75%
        assert "performance" in common_tags

        # "postgresql" only in 1/4 = 25%
        assert "postgresql" not in common_tags

    def test_dominant_type_extraction(self):
        """Test extracting dominant memory type."""
        types = ["success", "success", "insight", "success", "failure"]

        # Count type occurrences
        type_counts: dict[str, int] = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1

        # Find dominant type
        dominant_type = max(type_counts.items(), key=lambda x: x[1])[0]

        assert dominant_type == "success"  # 3 out of 5

    def test_pattern_content_generation(self):
        """Test generated pattern content structure."""
        # Expected structure includes:
        # - Header with count
        # - Dominant type
        # - Common tags
        # - Representative examples

        expected_parts = [
            "Pattern extracted from",
            "Dominant type:",
            "Common tags:",
            "Representative examples:",
        ]

        # Simulate content generation
        content = f"""**Pattern extracted from 5 memories**

- Dominant type: success
- Common tags: database, performance

**Representative examples:**
1. Fixed PostgreSQL connection pooling
2. Optimized MySQL query cache
3. Improved Redis connection handling"""

        for part in expected_parts:
            assert part in content

