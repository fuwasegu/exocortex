"""Unit tests for brain modules."""

from datetime import datetime, timedelta, timezone

import pytest

from exocortex.brain.hippocampus.dynamics import HybridScoreWeights, MemoryDynamics
from exocortex.brain.neocortex.patterns import ClusterAnalysis, PatternExtractor


class TestHybridScoreWeights:
    """Tests for HybridScoreWeights dataclass."""

    def test_default_weights(self) -> None:
        """Test default weight values."""
        weights = HybridScoreWeights()
        assert weights.similarity == 0.5
        assert weights.recency == 0.25
        assert weights.frequency == 0.15
        assert weights.frustration == 0.1

    def test_custom_weights(self) -> None:
        """Test custom weight values."""
        weights = HybridScoreWeights(
            similarity=0.4, recency=0.3, frequency=0.2, frustration=0.1
        )
        assert weights.similarity == 0.4
        assert weights.recency == 0.3
        assert weights.frequency == 0.2
        assert weights.frustration == 0.1

    def test_weights_must_sum_to_one(self) -> None:
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            HybridScoreWeights(similarity=0.5, recency=0.5, frequency=0.5, frustration=0.5)


class TestMemoryDynamics:
    """Tests for MemoryDynamics calculator."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        dynamics = MemoryDynamics()
        assert dynamics.weights is not None
        assert dynamics.decay_half_life_days == 30.0

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        weights = HybridScoreWeights()
        dynamics = MemoryDynamics(weights=weights, decay_half_life_days=60.0)
        assert dynamics.decay_half_life_days == 60.0

    def test_recency_score_recent_access(self) -> None:
        """Test recency score for recently accessed memory."""
        dynamics = MemoryDynamics()
        now = datetime.now(timezone.utc)
        last_accessed = now - timedelta(hours=1)

        score = dynamics.compute_recency_score(last_accessed, now)
        # Should be very close to 1.0 for recent access
        assert score > 0.99

    def test_recency_score_old_access(self) -> None:
        """Test recency score for old memory."""
        dynamics = MemoryDynamics(decay_half_life_days=30.0)
        now = datetime.now(timezone.utc)
        last_accessed = now - timedelta(days=30)

        score = dynamics.compute_recency_score(last_accessed, now)
        # Should be around 0.5 after one half-life
        assert 0.45 < score < 0.55

    def test_recency_score_very_old_access(self) -> None:
        """Test recency score for very old memory."""
        dynamics = MemoryDynamics(decay_half_life_days=30.0)
        now = datetime.now(timezone.utc)
        last_accessed = now - timedelta(days=90)  # 3 half-lives

        score = dynamics.compute_recency_score(last_accessed, now)
        # Should be around 0.125 (2^-3) after three half-lives
        assert 0.1 < score < 0.15

    def test_recency_score_none_access(self) -> None:
        """Test recency score when last_accessed_at is None."""
        dynamics = MemoryDynamics()
        score = dynamics.compute_recency_score(None)
        assert score == 0.5  # Default for unknown

    def test_frequency_score_high_access(self) -> None:
        """Test frequency score for high access count."""
        dynamics = MemoryDynamics()
        score = dynamics.compute_frequency_score(access_count=100, max_access_count=100)
        assert score == 1.0

    def test_frequency_score_low_access(self) -> None:
        """Test frequency score for low access count."""
        dynamics = MemoryDynamics()
        score = dynamics.compute_frequency_score(access_count=1, max_access_count=100)
        # log(2) / log(101) ≈ 0.15
        assert 0.1 < score < 0.2

    def test_frequency_score_zero_max(self) -> None:
        """Test frequency score when max is zero."""
        dynamics = MemoryDynamics()
        score = dynamics.compute_frequency_score(access_count=5, max_access_count=0)
        assert score == 0.0

    def test_hybrid_score_calculation(self) -> None:
        """Test hybrid score calculation."""
        dynamics = MemoryDynamics()
        score = dynamics.compute_hybrid_score(
            similarity=1.0,
            recency_score=1.0,
            frequency_score=1.0,
            frustration_score=1.0,
        )
        # All 1.0 should give 1.0
        assert score == 1.0

    def test_hybrid_score_weighted(self) -> None:
        """Test hybrid score with different weights."""
        dynamics = MemoryDynamics()
        # Only similarity = 1.0, others = 0.0
        score = dynamics.compute_hybrid_score(
            similarity=1.0,
            recency_score=0.0,
            frequency_score=0.0,
            frustration_score=0.0,
        )
        # Should be 0.5 * 1.0 = 0.5
        assert score == 0.5


class TestPatternExtractor:
    """Tests for PatternExtractor."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        extractor = PatternExtractor()
        assert extractor.min_cluster_size == 3
        assert extractor.similarity_threshold == 0.7
        assert extractor.confidence_per_instance == 0.1
        assert extractor.max_confidence == 0.95

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        extractor = PatternExtractor(
            min_cluster_size=5,
            similarity_threshold=0.8,
            confidence_per_instance=0.05,
            max_confidence=0.9,
        )
        assert extractor.min_cluster_size == 5
        assert extractor.similarity_threshold == 0.8

    def test_analyze_cluster_common_tags(self) -> None:
        """Test cluster analysis extracts common tags."""
        extractor = PatternExtractor()
        tags_list = [
            ["python", "testing", "pytest"],
            ["python", "testing", "unittest"],
            ["python", "testing", "mock"],
        ]
        types_list = ["insight", "insight", "insight"]

        result = extractor.analyze_cluster(tags_list, types_list)

        assert "python" in result.common_tags
        assert "testing" in result.common_tags
        assert "pytest" not in result.common_tags  # Only in 1/3
        assert result.dominant_type == "insight"
        assert result.memory_count == 3

    def test_analyze_cluster_dominant_type(self) -> None:
        """Test cluster analysis finds dominant type."""
        extractor = PatternExtractor()
        tags_list = [["tag1"], ["tag2"], ["tag3"], ["tag4"]]
        types_list = ["insight", "insight", "decision", "insight"]

        result = extractor.analyze_cluster(tags_list, types_list)

        assert result.dominant_type == "insight"

    def test_analyze_cluster_with_similarities(self) -> None:
        """Test cluster analysis with similarity scores."""
        extractor = PatternExtractor()
        tags_list = [["tag1"], ["tag2"]]
        types_list = ["insight", "insight"]
        similarities = [0.8, 0.9]

        result = extractor.analyze_cluster(tags_list, types_list, similarities)

        assert result.avg_similarity == pytest.approx(0.85)

    def test_calculate_confidence_base(self) -> None:
        """Test confidence calculation with single instance."""
        extractor = PatternExtractor()
        confidence = extractor.calculate_confidence(instance_count=1)
        assert confidence == 0.5  # Base confidence

    def test_calculate_confidence_increases(self) -> None:
        """Test confidence increases with more instances."""
        extractor = PatternExtractor()
        conf1 = extractor.calculate_confidence(instance_count=1)
        conf5 = extractor.calculate_confidence(instance_count=5)

        assert conf5 > conf1
        # 0.5 + (5-1) * 0.1 = 0.9
        assert conf5 == 0.9

    def test_calculate_confidence_capped(self) -> None:
        """Test confidence is capped at max."""
        extractor = PatternExtractor(max_confidence=0.95)
        confidence = extractor.calculate_confidence(instance_count=100)
        assert confidence == 0.95

    def test_should_create_pattern_true(self) -> None:
        """Test pattern creation threshold - sufficient."""
        extractor = PatternExtractor(min_cluster_size=3)
        assert extractor.should_create_pattern(cluster_size=3) is True
        assert extractor.should_create_pattern(cluster_size=5) is True

    def test_should_create_pattern_false(self) -> None:
        """Test pattern creation threshold - insufficient."""
        extractor = PatternExtractor(min_cluster_size=3)
        assert extractor.should_create_pattern(cluster_size=2) is False
        assert extractor.should_create_pattern(cluster_size=1) is False


class TestClusterAnalysis:
    """Tests for ClusterAnalysis dataclass."""

    def test_creation(self) -> None:
        """Test ClusterAnalysis creation."""
        analysis = ClusterAnalysis(
            common_tags=["python", "testing"],
            dominant_type="insight",
            memory_count=5,
            avg_similarity=0.85,
        )
        assert analysis.common_tags == ["python", "testing"]
        assert analysis.dominant_type == "insight"
        assert analysis.memory_count == 5
        assert analysis.avg_similarity == 0.85

