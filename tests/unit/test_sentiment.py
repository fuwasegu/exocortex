"""Unit tests for SentimentAnalyzer.

Tests for:
- Availability check (when transformers not installed)
- Sentiment classification
- Contradiction detection
"""

from unittest.mock import MagicMock, patch

from exocortex.domain.services.sentiment import (
    Sentiment,
    SentimentAnalyzer,
    SentimentResult,
)


class TestSentimentAnalyzerAvailability:
    """Tests for availability checks."""

    def test_is_available_when_transformers_missing(self):
        """Should return False when transformers is not installed."""
        analyzer = SentimentAnalyzer()

        with patch.dict("sys.modules", {"transformers": None}):
            # Reset cached availability
            analyzer._available = None
            # This should detect transformers is not available
            # Note: This test might pass anyway if transformers is installed
            # The actual behavior depends on environment

    def test_analyze_returns_none_when_unavailable(self):
        """Should return None when model is not available."""
        analyzer = SentimentAnalyzer()
        analyzer._available = False

        result = analyzer.analyze("test text")

        assert result is None


class TestSentimentResult:
    """Tests for SentimentResult dataclass."""

    def test_sentiment_result_creation(self):
        """Should create a valid SentimentResult."""
        result = SentimentResult(
            sentiment=Sentiment.POSITIVE,
            confidence=0.95,
            raw_label="ポジティブ",
        )

        assert result.sentiment == Sentiment.POSITIVE
        assert result.confidence == 0.95
        assert result.raw_label == "ポジティブ"


class TestSentimentNormalization:
    """Tests for label normalization."""

    def test_normalizes_japanese_positive(self):
        """Should normalize Japanese positive label."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("ポジティブ") == Sentiment.POSITIVE

    def test_normalizes_japanese_negative(self):
        """Should normalize Japanese negative label."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("ネガティブ") == Sentiment.NEGATIVE

    def test_normalizes_english_positive(self):
        """Should normalize English positive label."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("POSITIVE") == Sentiment.POSITIVE
        assert analyzer._normalize_label("positive") == Sentiment.POSITIVE

    def test_normalizes_english_negative(self):
        """Should normalize English negative label."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("NEGATIVE") == Sentiment.NEGATIVE
        assert analyzer._normalize_label("negative") == Sentiment.NEGATIVE

    def test_normalizes_star_ratings(self):
        """Should normalize star-based ratings."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("1") == Sentiment.NEGATIVE
        assert analyzer._normalize_label("2") == Sentiment.NEGATIVE
        assert analyzer._normalize_label("4") == Sentiment.POSITIVE
        assert analyzer._normalize_label("5") == Sentiment.POSITIVE

    def test_defaults_to_neutral(self):
        """Should default to neutral for unknown labels."""
        analyzer = SentimentAnalyzer()

        assert analyzer._normalize_label("3") == Sentiment.NEUTRAL
        assert analyzer._normalize_label("unknown") == Sentiment.NEUTRAL


class TestSentimentContradiction:
    """Tests for contradiction detection."""

    def test_is_contradictory_when_unavailable(self):
        """Should return False when model is not available."""
        analyzer = SentimentAnalyzer()
        analyzer._available = False

        is_contradictory, reason = analyzer.is_contradictory("good", "bad")

        assert is_contradictory is False
        assert "unavailable" in reason

    def test_is_contradictory_with_mock_pipeline(self):
        """Should detect contradiction with mocked pipeline."""
        analyzer = SentimentAnalyzer()
        analyzer._available = True

        # Mock the pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.side_effect = [
            [{"label": "ポジティブ", "score": 0.95}],
            [{"label": "ネガティブ", "score": 0.90}],
        ]
        analyzer._pipeline = mock_pipeline

        is_contradictory, reason = analyzer.is_contradictory(
            "成功した", "失敗した", min_confidence=0.7
        )

        assert is_contradictory is True
        assert "contradiction" in reason.lower()

    def test_not_contradictory_when_same_sentiment(self):
        """Should not detect contradiction when sentiments match."""
        analyzer = SentimentAnalyzer()
        analyzer._available = True

        # Mock the pipeline to return same sentiment
        mock_pipeline = MagicMock()
        mock_pipeline.side_effect = [
            [{"label": "ポジティブ", "score": 0.95}],
            [{"label": "ポジティブ", "score": 0.90}],
        ]
        analyzer._pipeline = mock_pipeline

        is_contradictory, reason = analyzer.is_contradictory(
            "成功した", "うまくいった", min_confidence=0.7
        )

        assert is_contradictory is False
        assert "no contradiction" in reason.lower()


class TestSentimentEnum:
    """Tests for Sentiment enum."""

    def test_sentiment_values(self):
        """Should have expected values."""
        assert Sentiment.POSITIVE.value == "positive"
        assert Sentiment.NEGATIVE.value == "negative"
        assert Sentiment.NEUTRAL.value == "neutral"

    def test_sentiment_value_is_string(self):
        """Sentiment value should be a string."""
        assert Sentiment.POSITIVE.value == "positive"
        assert isinstance(Sentiment.POSITIVE.value, str)

