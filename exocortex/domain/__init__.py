"""Domain layer - Core business logic and models."""

from .exceptions import (
    DuplicateLinkError,
    ExocortexError,
    MemoryNotFoundError,
    ValidationError,
)
from .models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    KnowledgeInsight,
    Memory,
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
    StoreMemoryResult,
    SuggestedLink,
)

__all__ = [
    # Exceptions
    "ExocortexError",
    "MemoryNotFoundError",
    "DuplicateLinkError",
    "ValidationError",
    # Models
    "Memory",
    "MemoryType",
    "MemoryWithContext",
    "RelationType",
    "MemoryLink",
    "SuggestedLink",
    "KnowledgeInsight",
    "MemoryStats",
    "KnowledgeHealthIssue",
    "AnalyzeKnowledgeResult",
    "StoreMemoryResult",
]

