"""Sentiment Analysis using local BERT model.

This module provides optional sentiment analysis capabilities using
a local Japanese BERT model for more accurate contradiction detection.

The model is lazy-loaded to avoid startup overhead when not needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Sentiment(str, Enum):
    """Sentiment classification result."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class SentimentResult:
    """Result from sentiment analysis."""

    sentiment: Sentiment
    confidence: float
    raw_label: str  # Original model label


# Default model for Japanese sentiment analysis
DEFAULT_MODEL = "daigo/bert-base-japanese-sentiment"

# Fallback multilingual model
FALLBACK_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"


class SentimentAnalyzer:
    """Optional sentiment analysis using local BERT model.

    This analyzer uses a Japanese BERT model fine-tuned for sentiment
    classification. It provides more accurate positive/negative detection
    than keyword-based approaches.

    The model is lazy-loaded on first use to avoid startup overhead.

    Usage:
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("このアプローチは完璧に機能した")
        # SentimentResult(sentiment=Sentiment.POSITIVE, confidence=0.98, ...)

    Note:
        Requires optional dependencies: `pip install exocortex[sentiment]`
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        """Initialize the sentiment analyzer.

        Args:
            model_name: HuggingFace model name for sentiment analysis.
            device: Device to run inference on ('cpu' or 'cuda').
        """
        self._model_name = model_name
        self._device = device
        self._pipeline = None
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if sentiment analysis is available (dependencies installed)."""
        if self._available is not None:
            return self._available

        try:
            import transformers  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False
            logger.info(
                "Sentiment analysis not available. "
                "Install with: pip install exocortex[sentiment]"
            )

        return self._available

    def _load_pipeline(self) -> bool:
        """Lazy load the sentiment analysis pipeline."""
        if self._pipeline is not None:
            return True

        if not self.is_available():
            return False

        try:
            from transformers import pipeline

            logger.info(f"Loading sentiment model: {self._model_name}")
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self._model_name,
                device=self._device,
                truncation=True,
                max_length=512,
            )
            logger.info("Sentiment model loaded successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to load sentiment model: {e}")
            # Try fallback model
            try:
                logger.info(f"Trying fallback model: {FALLBACK_MODEL}")
                from transformers import pipeline

                self._pipeline = pipeline(
                    "sentiment-analysis",
                    model=FALLBACK_MODEL,
                    device=self._device,
                    truncation=True,
                    max_length=512,
                )
                logger.info("Fallback sentiment model loaded successfully")
                return True
            except Exception as e2:
                logger.error(f"Failed to load fallback model: {e2}")
                return False

    def analyze(self, text: str) -> SentimentResult | None:
        """Analyze sentiment of the given text.

        Args:
            text: Text to analyze (will be truncated to 512 tokens).

        Returns:
            SentimentResult with sentiment classification and confidence,
            or None if analysis failed.
        """
        if not self._load_pipeline():
            return None

        try:
            # Truncate very long text
            text = text[:2000]  # Pre-truncate before tokenization

            result = self._pipeline(text)[0]
            raw_label = result["label"]
            confidence = result["score"]

            # Normalize label to our Sentiment enum
            sentiment = self._normalize_label(raw_label)

            return SentimentResult(
                sentiment=sentiment,
                confidence=confidence,
                raw_label=raw_label,
            )
        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return None

    def _normalize_label(self, label: str) -> Sentiment:
        """Normalize model-specific labels to our Sentiment enum."""
        label_lower = label.lower()

        # Japanese model labels
        if "ポジティブ" in label or "positive" in label_lower:
            return Sentiment.POSITIVE
        if "ネガティブ" in label or "negative" in label_lower:
            return Sentiment.NEGATIVE

        # Star-based labels (1-5 stars)
        if label in ["1", "2", "1 star", "2 stars"]:
            return Sentiment.NEGATIVE
        if label in ["4", "5", "4 stars", "5 stars"]:
            return Sentiment.POSITIVE

        # Default to neutral
        return Sentiment.NEUTRAL

    def analyze_pair(
        self, text_a: str, text_b: str
    ) -> tuple[SentimentResult | None, SentimentResult | None]:
        """Analyze sentiment of two texts for comparison.

        Useful for contradiction detection.

        Returns:
            Tuple of (result_a, result_b).
        """
        result_a = self.analyze(text_a)
        result_b = self.analyze(text_b)
        return result_a, result_b

    def is_contradictory(
        self,
        text_a: str,
        text_b: str,
        min_confidence: float = 0.7,
    ) -> tuple[bool, str]:
        """Check if two texts have contradictory sentiments.

        Args:
            text_a: First text.
            text_b: Second text.
            min_confidence: Minimum confidence for both results.

        Returns:
            Tuple of (is_contradictory, reason).
        """
        result_a, result_b = self.analyze_pair(text_a, text_b)

        if result_a is None or result_b is None:
            return False, "sentiment analysis unavailable"

        if result_a.confidence < min_confidence or result_b.confidence < min_confidence:
            return False, "low confidence"

        # Check for sentiment contradiction
        if (
            result_a.sentiment == Sentiment.POSITIVE
            and result_b.sentiment == Sentiment.NEGATIVE
        ) or (
            result_a.sentiment == Sentiment.NEGATIVE
            and result_b.sentiment == Sentiment.POSITIVE
        ):
            return True, (
                f"sentiment contradiction: {result_a.sentiment.value} "
                f"({result_a.confidence:.2f}) vs {result_b.sentiment.value} "
                f"({result_b.confidence:.2f})"
            )

        return False, "no contradiction"


# Global singleton for convenience
_global_analyzer: SentimentAnalyzer | None = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get the global sentiment analyzer instance."""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = SentimentAnalyzer()
    return _global_analyzer

