"""Sentiment Analysis for Frustration Detection.

Analyzes text content to detect frustration indicators and
emotional intensity. This is a lightweight, rule-based approach
that doesn't require external LLM calls.

Future enhancement: Optional LLM-based sentiment analysis for
more nuanced detection.
"""

import re
from dataclasses import dataclass


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    frustration_score: float  # 0.0 (calm) to 1.0 (extremely frustrated)
    confidence: float  # How confident we are in the score
    indicators: list[str]  # What triggered the score
    estimated_hours: float | None  # Estimated time spent (if detectable)


class SentimentAnalyzer:
    """Analyzes text for frustration and emotional intensity.

    Uses a combination of:
    - Keyword detection (negative words, frustration indicators)
    - Pattern matching (time expressions, exclamation marks)
    - Structural analysis (caps, punctuation patterns)
    """

    # Frustration keywords with weights (0.0-1.0)
    FRUSTRATION_KEYWORDS: dict[str, float] = {
        # High frustration (0.8-1.0)
        "nightmare": 1.0,
        "impossible": 0.95,
        "hate": 0.9,
        "worst": 0.9,
        "terrible": 0.9,
        "hell": 0.9,
        "disaster": 0.9,
        "furious": 0.95,
        "rage": 0.95,
        # Medium-high frustration (0.6-0.8)
        "frustrated": 0.8,
        "frustrating": 0.8,
        "annoying": 0.7,
        "annoyed": 0.7,
        "stuck": 0.75,
        "blocked": 0.7,
        "waste": 0.7,
        "wasted": 0.75,
        "pain": 0.7,
        "painful": 0.75,
        "struggle": 0.7,
        "struggling": 0.75,
        "headache": 0.7,
        # Medium frustration (0.4-0.6)
        "finally": 0.5,  # Often indicates relief after struggle
        "hours": 0.4,  # Time spent indicator
        "days": 0.5,
        "weeks": 0.6,
        "confusing": 0.5,
        "confused": 0.5,
        "unclear": 0.45,
        "broken": 0.55,
        "bug": 0.4,
        "bugs": 0.45,
        "issue": 0.35,
        "problem": 0.4,
        "error": 0.35,
        "fail": 0.5,
        "failed": 0.55,
        "failure": 0.6,
        # Low frustration (0.2-0.4)
        "tricky": 0.3,
        "weird": 0.3,
        "strange": 0.3,
        "unexpected": 0.35,
        "workaround": 0.4,
        "hack": 0.35,
        "gotcha": 0.4,
    }

    # Japanese frustration keywords
    FRUSTRATION_KEYWORDS_JA: dict[str, float] = {
        # High frustration
        "最悪": 1.0,
        "地獄": 0.95,
        "絶望": 0.95,
        "クソ": 0.9,
        "死ぬ": 0.85,
        "殺す": 0.9,
        "ハマった": 0.8,
        "詰んだ": 0.85,
        # Medium-high
        "つらい": 0.75,
        "辛い": 0.75,
        "イライラ": 0.8,
        "困った": 0.6,
        "困る": 0.55,
        "面倒": 0.6,
        "めんどくさい": 0.65,
        "わからん": 0.5,
        "分からない": 0.45,
        # Medium
        "やっと": 0.5,  # "Finally" equivalent
        "時間かかった": 0.6,
        "バグ": 0.4,
        "エラー": 0.35,
        "失敗": 0.5,
    }

    # Time patterns for estimating hours spent
    TIME_PATTERNS = [
        (r"(\d+)\s*hours?", lambda m: float(m.group(1))),
        (r"(\d+)\s*時間", lambda m: float(m.group(1))),
        (r"(\d+)\s*days?", lambda m: float(m.group(1)) * 8),  # Assume 8h/day
        (r"(\d+)\s*日", lambda m: float(m.group(1)) * 8),
        (r"half\s*(?:a\s*)?day", lambda m: 4.0),
        (r"半日", lambda m: 4.0),
        (r"all\s*day", lambda m: 8.0),
        (r"一日中", lambda m: 8.0),
        (r"(\d+)\s*weeks?", lambda m: float(m.group(1)) * 40),
        (r"(\d+)\s*週間?", lambda m: float(m.group(1)) * 40),
    ]

    def analyze(
        self,
        content: str,
        is_painful: bool | None = None,
    ) -> SentimentResult:
        """Analyze content for frustration indicators.

        Args:
            content: The text content to analyze.
            is_painful: Optional explicit flag from user.
                       If True, sets minimum score of 0.7.
                       If False, caps score at 0.3.

        Returns:
            SentimentResult with frustration score and metadata.
        """
        content_lower = content.lower()
        indicators: list[str] = []
        scores: list[float] = []

        # 1. Keyword detection (English)
        for keyword, weight in self.FRUSTRATION_KEYWORDS.items():
            if keyword in content_lower:
                scores.append(weight)
                indicators.append(f"keyword:{keyword}")

        # 2. Keyword detection (Japanese)
        for keyword, weight in self.FRUSTRATION_KEYWORDS_JA.items():
            if keyword in content:
                scores.append(weight)
                indicators.append(f"keyword_ja:{keyword}")

        # 3. Exclamation marks (intensity indicator)
        exclamation_count = content.count("!")
        if exclamation_count >= 3:
            scores.append(0.6)
            indicators.append(f"exclamation:{exclamation_count}")
        elif exclamation_count >= 1:
            scores.append(0.3)
            indicators.append(f"exclamation:{exclamation_count}")

        # 4. ALL CAPS detection (shouting)
        caps_words = re.findall(r"\b[A-Z]{3,}\b", content)
        if len(caps_words) >= 2:
            scores.append(0.5)
            indicators.append(f"caps:{len(caps_words)}")

        # 5. Time spent estimation
        estimated_hours = self._extract_time_spent(content)
        if estimated_hours is not None:
            # More time = more frustration (capped at 0.8)
            time_score = min(0.8, estimated_hours / 20.0)  # 20h = max
            if time_score > 0.2:
                scores.append(time_score)
                indicators.append(f"time_spent:{estimated_hours}h")

        # Calculate base score (weighted average with boost for multiple indicators)
        if scores:
            base_score = sum(scores) / len(scores)
            # Boost for multiple indicators (frustration compounds)
            indicator_boost = min(0.2, len(indicators) * 0.03)
            base_score = min(1.0, base_score + indicator_boost)
        else:
            base_score = 0.0

        # Apply explicit is_painful flag
        if is_painful is True:
            base_score = max(0.7, base_score)
            indicators.append("explicit:is_painful=true")
        elif is_painful is False:
            base_score = min(0.3, base_score)
            indicators.append("explicit:is_painful=false")

        # Calculate confidence based on number of indicators
        confidence = min(1.0, 0.3 + len(indicators) * 0.15)

        return SentimentResult(
            frustration_score=round(base_score, 3),
            confidence=round(confidence, 3),
            indicators=indicators,
            estimated_hours=estimated_hours,
        )

    def _extract_time_spent(self, content: str) -> float | None:
        """Extract estimated time spent from content.

        Returns:
            Estimated hours, or None if not detectable.
        """
        content_lower = content.lower()
        max_hours: float | None = None

        for pattern, extractor in self.TIME_PATTERNS:
            match = re.search(pattern, content_lower, re.IGNORECASE)
            if match:
                hours = extractor(match)
                if max_hours is None or hours > max_hours:
                    max_hours = hours

        return max_hours
