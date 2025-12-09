"""Memory Dynamics - Recency and Frequency tracking.

Implements the Memory Dynamics system that tracks:
- last_accessed_at: When was this memory last recalled?
- access_count: How many times has this been accessed?
- decay_rate: How quickly does this memory fade?

These metrics enable hybrid scoring that combines:
- Vector similarity (semantic relevance)
- Recency (temporal relevance)
- Frequency (importance by usage)
- Frustration (emotional weight)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class HybridScoreWeights:
    """Weights for hybrid scoring components."""

    similarity: float = 0.5
    recency: float = 0.25
    frequency: float = 0.15
    frustration: float = 0.1

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = self.similarity + self.recency + self.frequency + self.frustration
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Weights must sum to 1.0, got {total}")


class MemoryDynamics:
    """Handles memory dynamics calculations.

    This class encapsulates the logic for:
    - Computing recency scores based on time decay
    - Computing frequency scores from access counts
    - Applying hybrid scoring to search results
    """

    def __init__(
        self,
        weights: HybridScoreWeights | None = None,
        decay_half_life_days: float = 30.0,
    ) -> None:
        """Initialize memory dynamics calculator.

        Args:
            weights: Weights for hybrid scoring components
            decay_half_life_days: Half-life for recency decay (default 30 days)
        """
        self.weights = weights or HybridScoreWeights()
        self.decay_half_life_days = decay_half_life_days

    def compute_recency_score(
        self,
        last_accessed_at: datetime | None,
        reference_time: datetime | None = None,
    ) -> float:
        """Compute recency score using exponential decay.

        Args:
            last_accessed_at: When the memory was last accessed
            reference_time: Reference time for comparison (default: now)

        Returns:
            Recency score between 0.0 and 1.0
        """
        if last_accessed_at is None:
            return 0.5  # Default for memories without access history

        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Ensure timezone awareness
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        days_since_access = (reference_time - last_accessed_at).total_seconds() / 86400

        # Exponential decay: e^(-0.693 * t / half_life)
        # 0.693 is ln(2), making this true half-life decay
        decay_factor = -0.693 * days_since_access / self.decay_half_life_days
        return math.exp(decay_factor)

    def compute_frequency_score(
        self,
        access_count: int,
        max_access_count: int,
    ) -> float:
        """Compute frequency score using log normalization.

        Args:
            access_count: Number of times this memory was accessed
            max_access_count: Maximum access count in the result set

        Returns:
            Frequency score between 0.0 and 1.0
        """
        if max_access_count <= 0:
            return 0.0

        # Log normalization to prevent high-frequency memories from dominating
        return math.log1p(access_count) / math.log1p(max_access_count)

    def compute_hybrid_score(
        self,
        similarity: float,
        recency_score: float,
        frequency_score: float,
        frustration_score: float,
    ) -> float:
        """Compute weighted hybrid score.

        Args:
            similarity: Vector similarity score (0.0-1.0)
            recency_score: Recency score (0.0-1.0)
            frequency_score: Frequency score (0.0-1.0)
            frustration_score: Frustration/emotional score (0.0-1.0)

        Returns:
            Weighted hybrid score
        """
        return (
            self.weights.similarity * similarity
            + self.weights.recency * recency_score
            + self.weights.frequency * frequency_score
            + self.weights.frustration * frustration_score
        )
