"""Domain Services Package.

This package contains the business logic layer for Exocortex.

Main components:
- MemoryService: Main service class (facade/coordinator)
- MemoryAnalyzer: New memory analysis and insight detection
- KnowledgeHealthAnalyzer: Knowledge base health analysis
- PatternConsolidator: Pattern extraction from memory clusters
- CuriosityEngine: AI that questions and wonders about the knowledge base
"""

from .analyzer import MemoryAnalyzer
from .curiosity import CuriosityEngine, CuriosityReport
from .health import KnowledgeHealthAnalyzer
from .memory import MemoryService
from .pattern import PatternConsolidator
from .sentiment import Sentiment, SentimentAnalyzer, SentimentResult

__all__ = [
    "MemoryService",
    "MemoryAnalyzer",
    "KnowledgeHealthAnalyzer",
    "PatternConsolidator",
    "CuriosityEngine",
    "CuriosityReport",
    "SentimentAnalyzer",
    "Sentiment",
    "SentimentResult",
]
