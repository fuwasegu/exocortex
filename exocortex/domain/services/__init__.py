"""Domain Services Package.

This package contains the business logic layer for Exocortex.

Main components:
- MemoryService: Main service class (facade/coordinator)
- MemoryAnalyzer: New memory analysis and insight detection
- KnowledgeHealthAnalyzer: Knowledge base health analysis
- PatternConsolidator: Pattern extraction from memory clusters
"""

from .analyzer import MemoryAnalyzer
from .health import KnowledgeHealthAnalyzer
from .memory import MemoryService
from .pattern import PatternConsolidator

__all__ = [
    "MemoryService",
    "MemoryAnalyzer",
    "KnowledgeHealthAnalyzer",
    "PatternConsolidator",
]

