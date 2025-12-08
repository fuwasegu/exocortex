"""Unit tests for Frustration Indexing (Phase 2.0 - Somatic Marker Hypothesis).

Tests the brain/amygdala module which handles emotional processing
and frustration scoring for memories.
"""

import pytest

from exocortex.brain.amygdala.frustration import FrustrationIndex, FrustrationIndexer
from exocortex.brain.amygdala.sentiment import SentimentAnalyzer, SentimentResult


class TestSentimentAnalyzer:
    """Tests for SentimentAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        return SentimentAnalyzer()

    def test_neutral_content(self, analyzer: SentimentAnalyzer) -> None:
        """Test neutral content returns low frustration score."""
        result = analyzer.analyze("Added a new feature to the user profile page.")
        assert result.frustration_score < 0.3
        assert result.confidence > 0

    def test_high_frustration_keywords(self, analyzer: SentimentAnalyzer) -> None:
        """Test high frustration keywords are detected."""
        content = "This bug was a nightmare to debug! Absolutely impossible!"
        result = analyzer.analyze(content)
        assert result.frustration_score >= 0.7
        assert (
            "keyword:nightmare" in result.indicators
            or "keyword:impossible" in result.indicators
        )

    def test_medium_frustration_keywords(self, analyzer: SentimentAnalyzer) -> None:
        """Test medium frustration keywords are detected."""
        content = "I was stuck on this bug for a while. Finally fixed it."
        result = analyzer.analyze(content)
        assert 0.3 <= result.frustration_score <= 0.7
        assert any("keyword:" in ind for ind in result.indicators)

    def test_exclamation_marks_boost_score(self, analyzer: SentimentAnalyzer) -> None:
        """Test that multiple exclamation marks are detected."""
        content = "Something went wrong!!!"
        result = analyzer.analyze(content)
        # Exclamation marks should be detected as indicator
        assert any("exclamation:" in ind for ind in result.indicators)

    def test_caps_boost_score(self, analyzer: SentimentAnalyzer) -> None:
        """Test that ALL CAPS words boost the score."""
        content = "WHY IS THIS NOT WORKING?!"
        result = analyzer.analyze(content)
        assert result.frustration_score > 0.3
        assert any("caps:" in ind for ind in result.indicators)

    def test_time_extraction_hours(self, analyzer: SentimentAnalyzer) -> None:
        """Test time extraction from content."""
        content = "Spent 5 hours debugging this issue."
        result = analyzer.analyze(content)
        assert result.estimated_hours == 5.0

    def test_time_extraction_days(self, analyzer: SentimentAnalyzer) -> None:
        """Test time extraction for days."""
        content = "This took 2 days to figure out."
        result = analyzer.analyze(content)
        assert result.estimated_hours == 16.0  # 2 days * 8 hours

    def test_japanese_keywords(self, analyzer: SentimentAnalyzer) -> None:
        """Test Japanese frustration keywords."""
        content = "このバグにハマった。最悪だった。"
        result = analyzer.analyze(content)
        assert result.frustration_score >= 0.6
        assert any("keyword_ja:" in ind for ind in result.indicators)

    def test_explicit_is_painful_true(self, analyzer: SentimentAnalyzer) -> None:
        """Test explicit is_painful=True flag."""
        content = "Fixed a bug."
        result = analyzer.analyze(content, is_painful=True)
        assert result.frustration_score >= 0.7
        assert "explicit:is_painful=true" in result.indicators

    def test_explicit_is_painful_false(self, analyzer: SentimentAnalyzer) -> None:
        """Test explicit is_painful=False flag caps score."""
        content = "This was a nightmare to debug!"
        result = analyzer.analyze(content, is_painful=False)
        assert result.frustration_score <= 0.3
        assert "explicit:is_painful=false" in result.indicators


class TestFrustrationIndexer:
    """Tests for FrustrationIndexer class."""

    @pytest.fixture
    def indexer(self) -> FrustrationIndexer:
        return FrustrationIndexer()

    def test_index_neutral_content(self, indexer: FrustrationIndexer) -> None:
        """Test indexing neutral content."""
        result = indexer.index("Added a new feature.")
        assert result.frustration_score < 0.2
        assert result.pain_level == "none"
        assert result.boost_factor == pytest.approx(1.0, abs=0.1)

    def test_index_painful_content(self, indexer: FrustrationIndexer) -> None:
        """Test indexing painful content."""
        result = indexer.index("This was a nightmare! Spent 8 hours debugging!")
        assert result.frustration_score >= 0.5
        assert result.pain_level in ("medium", "high", "extreme")
        assert result.boost_factor > 1.0

    def test_index_with_explicit_time(self, indexer: FrustrationIndexer) -> None:
        """Test indexing with explicit time_cost_hours."""
        result = indexer.index(
            "Fixed a bug.",
            time_cost_hours=10.0,
        )
        assert result.time_cost_hours == 10.0

    def test_pain_level_mapping(self, indexer: FrustrationIndexer) -> None:
        """Test pain level string mapping."""
        assert indexer._score_to_level(0.0) == "none"
        assert indexer._score_to_level(0.1) == "none"
        assert indexer._score_to_level(0.25) == "low"
        assert indexer._score_to_level(0.45) == "medium"
        assert indexer._score_to_level(0.65) == "high"
        assert indexer._score_to_level(0.9) == "extreme"

    def test_boost_factor_calculation(self, indexer: FrustrationIndexer) -> None:
        """Test boost factor calculation."""
        # boost = 1.0 + (score * 2.0)
        assert indexer._calculate_boost(0.0) == pytest.approx(1.0)
        assert indexer._calculate_boost(0.5) == pytest.approx(2.0)
        assert indexer._calculate_boost(1.0) == pytest.approx(3.0)

    def test_apply_frustration_boost(self, indexer: FrustrationIndexer) -> None:
        """Test applying frustration boost to search score."""
        base_score = 0.5
        frustration_score = 0.8

        boosted = indexer.apply_frustration_boost(
            base_score, frustration_score, w_frustration=0.15
        )

        expected = base_score + (frustration_score * 0.15)
        assert boosted == pytest.approx(expected)

    def test_pain_emoji(self, indexer: FrustrationIndexer) -> None:
        """Test pain emoji representation."""
        assert indexer.get_pain_emoji(0.0) == ""
        assert indexer.get_pain_emoji(0.1) == ""
        assert indexer.get_pain_emoji(0.25) == "😓"
        assert indexer.get_pain_emoji(0.5) == "🔥"
        assert indexer.get_pain_emoji(0.7) == "🔥🔥"
        assert indexer.get_pain_emoji(0.9) == "🔥🔥🔥"


class TestFrustrationIntegration:
    """Integration tests for frustration scoring in the memory system."""

    def test_sentiment_result_dataclass(self) -> None:
        """Test SentimentResult dataclass."""
        result = SentimentResult(
            frustration_score=0.75,
            confidence=0.85,
            indicators=["keyword:frustrated", "exclamation:3"],
            estimated_hours=4.0,
        )
        assert result.frustration_score == 0.75
        assert result.confidence == 0.85
        assert len(result.indicators) == 2
        assert result.estimated_hours == 4.0

    def test_frustration_index_dataclass(self) -> None:
        """Test FrustrationIndex dataclass."""
        index = FrustrationIndex(
            frustration_score=0.8,
            time_cost_hours=6.0,
            pain_level="high",
            boost_factor=2.6,
        )
        assert index.frustration_score == 0.8
        assert index.time_cost_hours == 6.0
        assert index.pain_level == "high"
        assert index.boost_factor == 2.6

    def test_indexer_with_custom_analyzer(self) -> None:
        """Test creating indexer with custom analyzer."""
        custom_analyzer = SentimentAnalyzer()
        indexer = FrustrationIndexer(analyzer=custom_analyzer)
        assert indexer.analyzer is custom_analyzer


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        return SentimentAnalyzer()

    @pytest.fixture
    def indexer(self) -> FrustrationIndexer:
        return FrustrationIndexer()

    def test_empty_content(self, analyzer: SentimentAnalyzer) -> None:
        """Test empty content."""
        result = analyzer.analyze("")
        assert result.frustration_score == 0.0
        assert result.estimated_hours is None

    def test_unicode_content(self, analyzer: SentimentAnalyzer) -> None:
        """Test content with unicode characters."""
        content = "🔥 This bug was terrible! 最悪だ！"
        result = analyzer.analyze(content)
        assert result.frustration_score > 0.5

    def test_very_long_content(self, analyzer: SentimentAnalyzer) -> None:
        """Test very long content."""
        content = "This was frustrating. " * 1000
        result = analyzer.analyze(content)
        assert 0 <= result.frustration_score <= 1.0

    def test_score_bounds(self, indexer: FrustrationIndexer) -> None:
        """Test that scores are always within bounds."""
        contents = [
            "",
            "Normal text",
            "NIGHTMARE IMPOSSIBLE HATE TERRIBLE FURIOUS!!!",
            "最悪！地獄！絶望！クソ！ハマった！" * 10,
        ]
        for content in contents:
            result = indexer.index(content)
            assert 0.0 <= result.frustration_score <= 1.0
            assert result.boost_factor >= 1.0
            assert result.boost_factor <= 3.0


class TestTimePatterns:
    """Test various time pattern extraction."""

    @pytest.fixture
    def analyzer(self) -> SentimentAnalyzer:
        return SentimentAnalyzer()

    def test_hours_variations(self, analyzer: SentimentAnalyzer) -> None:
        """Test various hour patterns."""
        test_cases = [
            ("3 hours", 3.0),
            ("3hours", 3.0),
            ("1 hour", 1.0),
            ("10 hours", 10.0),
        ]
        for content, expected in test_cases:
            result = analyzer.analyze(content)
            assert result.estimated_hours == expected, f"Failed for: {content}"

    def test_japanese_time(self, analyzer: SentimentAnalyzer) -> None:
        """Test Japanese time patterns."""
        test_cases = [
            ("3時間かかった", 3.0),
            ("半日", 4.0),
            ("一日中", 8.0),
            ("2週間", 80.0),  # 2 * 40
        ]
        for content, expected in test_cases:
            result = analyzer.analyze(content)
            assert result.estimated_hours == expected, f"Failed for: {content}"

    def test_multiple_time_units(self, analyzer: SentimentAnalyzer) -> None:
        """Test that different time units are compared for max."""
        # Different units (hours vs days) - should return larger value
        content = "Spent 2 hours initially, then it took 1 day to fully fix."
        result = analyzer.analyze(content)
        assert result.estimated_hours == 8.0  # 1 day = 8 hours > 2 hours
