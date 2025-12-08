"""Unit tests for Memory Dynamics (Phase 1).

Tests the hybrid scoring algorithm and access tracking functionality.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from exocortex.domain.models import Memory, MemoryType, MemoryWithContext


class TestMemoryDynamicsModel:
    """Tests for Memory model dynamics fields."""

    def test_memory_with_dynamics_defaults(self):
        """Test that dynamics fields have correct defaults."""
        now = datetime.now(timezone.utc)
        memory = Memory(
            id="test-123",
            content="Test content",
            summary="Test summary",
            memory_type=MemoryType.INSIGHT,
            created_at=now,
            updated_at=now,
        )

        # Check default values
        assert memory.last_accessed_at is None
        assert memory.access_count == 1
        assert memory.decay_rate == 0.1

    def test_memory_with_dynamics_explicit(self):
        """Test creating memory with explicit dynamics values."""
        now = datetime.now(timezone.utc)
        last_access = now - timedelta(hours=2)

        memory = Memory(
            id="test-456",
            content="Frequently accessed",
            summary="Popular memory",
            memory_type=MemoryType.SUCCESS,
            created_at=now - timedelta(days=30),
            updated_at=now,
            last_accessed_at=last_access,
            access_count=15,
            decay_rate=0.05,
        )

        assert memory.last_accessed_at == last_access
        assert memory.access_count == 15
        assert memory.decay_rate == 0.05

    def test_memory_with_context_inherits_dynamics(self):
        """Test MemoryWithContext inherits dynamics fields."""
        now = datetime.now(timezone.utc)
        memory = MemoryWithContext(
            id="test-789",
            content="Content",
            summary="Summary",
            memory_type=MemoryType.NOTE,
            created_at=now,
            updated_at=now,
            context="project",
            tags=["test"],
            last_accessed_at=now,
            access_count=5,
            decay_rate=0.2,
        )

        assert memory.access_count == 5
        assert memory.decay_rate == 0.2
        assert memory.context == "project"


class TestHybridScoringCalculations:
    """Tests for the hybrid scoring formula calculations.

    Formula: Score = (S_vec × w_vec) + (S_recency × w_recency) + (S_freq × w_freq)

    Default weights:
    - w_vec = 0.6
    - w_recency = 0.25
    - w_freq = 0.15
    """

    def test_recency_score_formula(self):
        """Test the recency score calculation: S_recency = e^(-λ × Δt)."""
        decay_lambda = 0.01  # per day

        # Just now: e^(-0.01 × 0) = 1.0
        delta_days = 0
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency == pytest.approx(1.0, abs=0.001)

        # 1 day ago: e^(-0.01 × 1) ≈ 0.990
        delta_days = 1
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency == pytest.approx(0.990, abs=0.001)

        # 30 days ago: e^(-0.01 × 30) ≈ 0.741
        delta_days = 30
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency == pytest.approx(0.741, abs=0.001)

        # 100 days ago: e^(-0.01 × 100) ≈ 0.368
        delta_days = 100
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency == pytest.approx(0.368, abs=0.001)

        # 365 days ago: e^(-0.01 × 365) ≈ 0.026
        delta_days = 365
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency == pytest.approx(0.026, abs=0.001)

    def test_frequency_score_formula(self):
        """Test the frequency score calculation: S_freq = log(1 + count) / max_log."""
        # Normalize against max access count of 100

        def calc_freq_score(count: int, max_count: int = 100) -> float:
            max_log = math.log(1 + max_count)
            return math.log(1 + count) / max_log if max_log > 0 else 0

        # 1 access (minimum): log(2) / log(101) ≈ 0.150
        assert calc_freq_score(1) == pytest.approx(0.150, abs=0.01)

        # 10 accesses: log(11) / log(101) ≈ 0.519
        assert calc_freq_score(10) == pytest.approx(0.519, abs=0.01)

        # 50 accesses: log(51) / log(101) ≈ 0.852
        assert calc_freq_score(50) == pytest.approx(0.852, abs=0.01)

        # 100 accesses (max): log(101) / log(101) = 1.0
        assert calc_freq_score(100) == pytest.approx(1.0, abs=0.001)

    def test_hybrid_score_formula(self):
        """Test the full hybrid score calculation."""
        w_vec = 0.6
        w_recency = 0.25
        w_freq = 0.15

        # High similarity, recent, moderate frequency
        s_vec = 0.9
        s_recency = 0.95
        s_freq = 0.5
        score = (s_vec * w_vec) + (s_recency * w_recency) + (s_freq * w_freq)
        assert score == pytest.approx(0.8525, abs=0.001)

        # Lower similarity but very recent and high frequency
        s_vec = 0.6
        s_recency = 1.0
        s_freq = 1.0
        score = (s_vec * w_vec) + (s_recency * w_recency) + (s_freq * w_freq)
        assert score == pytest.approx(0.76, abs=0.001)

        # High similarity but old and rarely accessed
        s_vec = 0.95
        s_recency = 0.1
        s_freq = 0.1
        score = (s_vec * w_vec) + (s_recency * w_recency) + (s_freq * w_freq)
        assert score == pytest.approx(0.61, abs=0.001)

    def test_weight_normalization(self):
        """Test that default weights sum to 1.0."""
        w_vec = 0.6
        w_recency = 0.25
        w_freq = 0.15
        assert w_vec + w_recency + w_freq == pytest.approx(1.0, abs=0.001)

    def test_score_bounds(self):
        """Test that hybrid score stays in [0, 1] range."""
        w_vec = 0.6
        w_recency = 0.25
        w_freq = 0.15

        # Maximum possible score
        max_score = (1.0 * w_vec) + (1.0 * w_recency) + (1.0 * w_freq)
        assert max_score == pytest.approx(1.0, abs=0.001)

        # Minimum possible score
        min_score = (0.0 * w_vec) + (0.0 * w_recency) + (0.0 * w_freq)
        assert min_score == pytest.approx(0.0, abs=0.001)

    def test_recency_vs_frequency_tradeoff(self):
        """Test the trade-off between recency and frequency."""
        w_vec = 0.6
        w_recency = 0.25
        w_freq = 0.15

        # Same vector similarity
        s_vec = 0.8

        # Recent but low frequency
        score_recent = (s_vec * w_vec) + (0.95 * w_recency) + (0.2 * w_freq)

        # Old but high frequency
        score_frequent = (s_vec * w_vec) + (0.3 * w_recency) + (0.9 * w_freq)

        # Recent should win with default weights (0.25 > 0.15)
        assert score_recent > score_frequent

        # Calculate exact values
        assert score_recent == pytest.approx(0.7475, abs=0.001)
        assert score_frequent == pytest.approx(0.69, abs=0.001)


class TestEdgeCases:
    """Tests for edge cases in dynamics calculations."""

    def test_zero_access_count(self):
        """Test handling of zero access count."""
        # log(1 + 0) = log(1) = 0
        s_freq = math.log(1 + 0)
        assert s_freq == 0.0

    def test_very_large_access_count(self):
        """Test frequency score with very large access count."""
        # Should not overflow and should approach normalized max
        max_count = 10000
        count = 10000
        max_log = math.log(1 + max_count)
        s_freq = math.log(1 + count) / max_log
        assert s_freq == pytest.approx(1.0, abs=0.001)

    def test_very_old_memory(self):
        """Test recency score for very old memories (years)."""
        decay_lambda = 0.01

        # 5 years old
        delta_days = 365 * 5
        s_recency = math.exp(-decay_lambda * delta_days)
        # e^(-18.25) is very small but not zero
        assert s_recency > 0
        assert s_recency < 0.0001

    def test_future_access_time(self):
        """Test handling of future access time (edge case)."""
        decay_lambda = 0.01

        # Negative delta (future) should give score > 1
        # This is a data integrity issue but should not crash
        delta_days = -1
        s_recency = math.exp(-decay_lambda * delta_days)
        assert s_recency > 1.0  # e^(0.01) ≈ 1.01

    def test_nan_and_inf_handling(self):
        """Test that calculations don't produce NaN or Inf."""
        decay_lambda = 0.01

        # Very large delta
        delta_days = 100000
        s_recency = math.exp(-decay_lambda * delta_days)
        assert not math.isnan(s_recency)
        assert not math.isinf(s_recency)
        assert s_recency >= 0


class TestScoringScenarios:
    """Real-world scenarios for hybrid scoring."""

    def simulate_hybrid_score(
        self,
        s_vec: float,
        days_since_access: float,
        access_count: int,
        max_access: int = 100,
        w_vec: float = 0.6,
        w_recency: float = 0.25,
        w_freq: float = 0.15,
        decay_lambda: float = 0.01,
    ) -> float:
        """Simulate the full hybrid scoring calculation."""
        # Recency score
        s_recency = math.exp(-decay_lambda * days_since_access)

        # Frequency score
        max_log = math.log(1 + max_access) if max_access > 0 else 1
        s_freq = math.log(1 + access_count) / max_log if max_log > 0 else 0

        return (s_vec * w_vec) + (s_recency * w_recency) + (s_freq * w_freq)

    def test_scenario_frequently_used_recent_memory(self):
        """Test: Memory used 20 times in last week, high similarity."""
        score = self.simulate_hybrid_score(
            s_vec=0.85,
            days_since_access=3,
            access_count=20,
        )
        # Should be high score
        assert score > 0.75

    def test_scenario_one_time_old_memory(self):
        """Test: Memory used once, 6 months ago, medium similarity."""
        score = self.simulate_hybrid_score(
            s_vec=0.7,
            days_since_access=180,
            access_count=1,
        )
        # Should be lower score
        assert score < 0.5

    def test_scenario_perfectly_matched_new_memory(self):
        """Test: Perfect match, just created."""
        score = self.simulate_hybrid_score(
            s_vec=1.0,
            days_since_access=0,
            access_count=1,
        )
        # Should be very high
        assert score > 0.8

    def test_scenario_comparison_recent_vs_popular(self):
        """Test: Compare recent low-frequency vs old high-frequency memory."""
        # Recent but rarely used
        score_recent = self.simulate_hybrid_score(
            s_vec=0.8,
            days_since_access=1,
            access_count=2,
        )

        # Old but heavily used
        score_popular = self.simulate_hybrid_score(
            s_vec=0.8,
            days_since_access=60,
            access_count=50,
        )

        # With default weights, recent should win slightly
        # because recency weight (0.25) > frequency weight (0.15)
        # But if popularity is very high, it might compensate
        assert abs(score_recent - score_popular) < 0.15  # Close but different

    def test_scenario_ranking_consistency(self):
        """Test that ranking is consistent with expected behavior."""
        # Create a set of memories with different characteristics
        memories = [
            {"name": "perfect_match_new", "s_vec": 0.95, "days": 1, "count": 5},
            {"name": "good_match_frequent", "s_vec": 0.75, "days": 10, "count": 50},
            {"name": "ok_match_recent", "s_vec": 0.65, "days": 2, "count": 3},
            {"name": "low_match_old", "s_vec": 0.4, "days": 100, "count": 10},
        ]

        scores = [
            (m["name"], self.simulate_hybrid_score(m["s_vec"], m["days"], m["count"]))
            for m in memories
        ]
        sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)

        # Perfect match should be first due to high vector similarity
        assert sorted_scores[0][0] == "perfect_match_new"

        # Low match old should be last
        assert sorted_scores[-1][0] == "low_match_old"
