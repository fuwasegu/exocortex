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


class SuggestedAction(BaseModel):
    """A suggested action for the agent to take."""

    tool: str = Field(..., description="Tool name to call")
    priority: str = Field(default="medium", description="Priority: high, medium, low")
    reason: str = Field(..., description="Why this action is suggested")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Suggested parameters for the tool"
    )


class SessionBriefing(BaseModel):
    """Briefing for the start of a session.

    Provides context about the current state of the knowledge base
    and suggests actions to take.
    """

    # Recent activity
    recent_memories: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Summary of recent memories (last 5)",
    )
    total_memories: int = Field(default=0, description="Total memories in the system")

    # Health status
    health_score: float = Field(
        default=100.0, description="Knowledge base health score (0-100)"
    )
    health_summary: str = Field(
        default="Healthy", description="Brief health status description"
    )

    # Issues detected
    pending_issues: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Issues that need attention (contradictions, outdated, etc.)",
    )

    # Suggested actions
    suggested_actions: list[SuggestedAction] = Field(
        default_factory=list,
        description="Recommended actions to take",
    )

    # Context-specific info
    context_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Memory count per context",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return self.model_dump(mode="json")
