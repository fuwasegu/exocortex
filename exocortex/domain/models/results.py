"""Result models for service operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .health import KnowledgeHealthIssue, KnowledgeInsight, SuggestedLink
from .memory import MemoryWithContext


class StoreMemoryResult(BaseModel):
    """Result of storing a memory."""

    success: bool
    memory_id: str
    summary: str
    suggested_links: list[SuggestedLink] = Field(
        default_factory=list,
        description="Suggested links to existing memories",
    )
    insights: list[KnowledgeInsight] = Field(
        default_factory=list,
        description="Insights about potential duplicates, contradictions, etc.",
    )


class RecallMemoriesResult(BaseModel):
    """Result of recalling memories."""

    memories: list[MemoryWithContext]
    total_found: int


class ListMemoriesResult(BaseModel):
    """Result of listing memories."""

    memories: list[MemoryWithContext]
    total_count: int
    has_more: bool


class MemoryStats(BaseModel):
    """Statistics about stored memories."""

    total_memories: int
    memories_by_type: dict[str, int]
    total_contexts: int
    total_tags: int
    top_tags: list[dict[str, Any]]


class AnalyzeKnowledgeResult(BaseModel):
    """Result of analyzing the knowledge base."""

    total_memories: int
    health_score: float = Field(..., description="Overall health score (0-100)")
    issues: list[KnowledgeHealthIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(
        default_factory=list, description="General improvement suggestions"
    )
    stats: dict[str, Any] = Field(
        default_factory=dict, description="Additional statistics"
    )
