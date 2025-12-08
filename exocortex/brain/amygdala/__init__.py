"""Amygdala Module - Emotional Processing.

The amygdala is responsible for processing emotions and
assigning emotional significance to memories. In Exocortex,
this module handles:

- Frustration Indexing: Scoring memories based on emotional intensity
- Sentiment Analysis: Detecting frustration and pain in content

Based on the Somatic Marker Hypothesis:
"Painful memories should be prioritized in decision-making"
"""

from exocortex.brain.amygdala.sentiment import SentimentAnalyzer
from exocortex.brain.amygdala.frustration import FrustrationIndexer

__all__ = ["SentimentAnalyzer", "FrustrationIndexer"]

