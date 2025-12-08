"""Frustration Indexing for Memory Prioritization.

Based on the Somatic Marker Hypothesis:
"Painful" memories (frustrating debugging sessions, difficult problems)
should be prioritized in recall to prevent repeating mistakes.

This module provides scoring and boosting logic for frustration-weighted
memory retrieval.
"""

from dataclasses import dataclass

from exocortex.brain.amygdala.sentiment import SentimentAnalyzer, SentimentResult


@dataclass
class FrustrationIndex:
    """Frustration index for a memory."""

    frustration_score: float  # 0.0 to 1.0
    time_cost_hours: float | None  # Estimated time spent
    pain_level: str  # "none", "low", "medium", "high", "extreme"
    boost_factor: float  # Multiplier for search ranking


class FrustrationIndexer:
    """Indexes and scores memories based on frustration level.

    Integrates with the hybrid scoring algorithm to boost
    painful memories in search results.
    """

    def __init__(self, analyzer: SentimentAnalyzer | None = None):
        """Initialize the indexer.

        Args:
            analyzer: Optional SentimentAnalyzer instance.
                     Creates a new one if not provided.
        """
        self.analyzer = analyzer or SentimentAnalyzer()

    def index(
        self,
        content: str,
        is_painful: bool | None = None,
        time_cost_hours: float | None = None,
    ) -> FrustrationIndex:
        """Calculate frustration index for content.

        Args:
            content: The memory content to analyze.
            is_painful: Optional explicit flag from user.
            time_cost_hours: Optional explicit time cost.

        Returns:
            FrustrationIndex with score and metadata.
        """
        # Analyze sentiment
        result: SentimentResult = self.analyzer.analyze(content, is_painful)

        # Use explicit time if provided, otherwise use detected
        final_hours = time_cost_hours or result.estimated_hours

        # Determine pain level
        pain_level = self._score_to_level(result.frustration_score)

        # Calculate boost factor for search ranking
        boost_factor = self._calculate_boost(result.frustration_score)

        return FrustrationIndex(
            frustration_score=result.frustration_score,
            time_cost_hours=final_hours,
            pain_level=pain_level,
            boost_factor=boost_factor,
        )

    def _score_to_level(self, score: float) -> str:
        """Convert numeric score to human-readable level.

        Args:
            score: Frustration score (0.0-1.0).

        Returns:
            Pain level string.
        """
        if score >= 0.8:
            return "extreme"
        elif score >= 0.6:
            return "high"
        elif score >= 0.4:
            return "medium"
        elif score >= 0.2:
            return "low"
        else:
            return "none"

    def _calculate_boost(self, score: float) -> float:
        """Calculate boost factor for search ranking.

        The boost factor is applied to the hybrid score during recall.
        Higher frustration = higher boost.

        Formula: boost = 1.0 + (score * 2.0)
        - score 0.0 -> boost 1.0 (no change)
        - score 0.5 -> boost 2.0 (2x weight)
        - score 1.0 -> boost 3.0 (3x weight)

        Args:
            score: Frustration score (0.0-1.0).

        Returns:
            Boost factor (1.0-3.0).
        """
        return 1.0 + (score * 2.0)

    def apply_frustration_boost(
        self,
        base_score: float,
        frustration_score: float,
        w_frustration: float = 0.15,
    ) -> float:
        """Apply frustration boost to a hybrid search score.

        Modifies the scoring formula:
        Original: Score = (S_vec * w_vec) + (S_recency * w_recency) + (S_freq * w_freq)
        New: Score = Original + (frustration_score * w_frustration)

        Args:
            base_score: The original hybrid score.
            frustration_score: Frustration score (0.0-1.0).
            w_frustration: Weight for frustration component.

        Returns:
            Boosted score.
        """
        frustration_component = frustration_score * w_frustration
        return base_score + frustration_component

    def get_pain_emoji(self, frustration_score: float) -> str:
        """Get emoji representation of pain level.

        Used for UI display to highlight painful memories.

        Args:
            frustration_score: Frustration score (0.0-1.0).

        Returns:
            Emoji string.
        """
        if frustration_score >= 0.8:
            return "🔥🔥🔥"  # Extreme pain
        elif frustration_score >= 0.6:
            return "🔥🔥"  # High pain
        elif frustration_score >= 0.4:
            return "🔥"  # Medium pain
        elif frustration_score >= 0.2:
            return "😓"  # Low pain
        else:
            return ""  # No pain indicator
