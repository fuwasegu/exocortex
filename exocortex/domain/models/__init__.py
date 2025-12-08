"""Domain models for Exocortex.

This package provides all domain models, organized by concern:
- enums: MemoryType, RelationType
- memory: Memory, MemoryLink, MemoryWithContext
- graph: Context, Tag
- pattern: Pattern, PatternInstance, PatternWithInstances
- health: SuggestedLink, KnowledgeInsight, KnowledgeHealthIssue
- results: StoreMemoryResult, RecallMemoriesResult, etc.
"""

from .enums import MemoryType, RelationType
from .graph import Context, Tag
from .health import KnowledgeHealthIssue, KnowledgeInsight, SuggestedLink
from .memory import Memory, MemoryLink, MemoryWithContext
from .pattern import Pattern, PatternInstance, PatternWithInstances
from .results import (
    AnalyzeKnowledgeResult,
    ListMemoriesResult,
    MemoryStats,
    RecallMemoriesResult,
    StoreMemoryResult,
)

__all__ = [
    # Enums
    "MemoryType",
    "RelationType",
    # Core models
    "Memory",
    "MemoryLink",
    "MemoryWithContext",
    # Graph models
    "Context",
    "Tag",
    # Pattern models
    "Pattern",
    "PatternInstance",
    "PatternWithInstances",
    # Health models
    "SuggestedLink",
    "KnowledgeInsight",
    "KnowledgeHealthIssue",
    # Result models
    "StoreMemoryResult",
    "RecallMemoriesResult",
    "ListMemoriesResult",
    "MemoryStats",
    "AnalyzeKnowledgeResult",
]

