"""Domain models for Exocortex."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Type of memory stored in Exocortex."""

    INSIGHT = "insight"  # General insights and learnings
    SUCCESS = "success"  # Successful solutions
    FAILURE = "failure"  # Failures and their causes
    DECISION = "decision"  # Technical decisions and reasoning
    NOTE = "note"  # General notes


class RelationType(str, Enum):
    """Type of relationship between memories."""

    RELATED = "related"  # Generally related memories
    SUPERSEDES = "supersedes"  # This memory updates/replaces the target
    CONTRADICTS = "contradicts"  # This memory contradicts the target
    EXTENDS = "extends"  # This memory extends/elaborates the target
    DEPENDS_ON = "depends_on"  # This memory depends on the target


# =============================================================================
# Core Domain Models
# =============================================================================


class Memory(BaseModel):
    """A memory stored in Exocortex."""

    id: str = Field(..., description="Unique identifier (UUID)")
    content: str = Field(..., description="Full content of the memory (Markdown)")
    summary: str = Field(..., description="Brief summary for search results")
    memory_type: MemoryType = Field(
        default=MemoryType.INSIGHT, description="Type of memory"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class MemoryLink(BaseModel):
    """A link between two memories."""

    target_id: str = Field(..., description="Target memory ID")
    target_summary: str | None = Field(None, description="Target memory summary")
    relation_type: RelationType = Field(..., description="Type of relationship")
    reason: str | None = Field(None, description="Reason for the link")
    created_at: datetime | None = Field(None, description="When the link was created")


class MemoryWithContext(Memory):
    """A memory with its associated context and tags."""

    context: str | None = Field(None, description="Associated context/project name")
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    similarity: float | None = Field(
        None, description="Similarity score (for search results)"
    )
    related_memories: list[MemoryLink] = Field(
        default_factory=list, description="Related memories"
    )


class Context(BaseModel):
    """A context (project/situation) in Exocortex."""

    name: str = Field(..., description="Context name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")


class Tag(BaseModel):
    """A tag in Exocortex."""

    name: str = Field(..., description="Tag name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")


# =============================================================================
# Knowledge Autonomy Models
# =============================================================================


class SuggestedLink(BaseModel):
    """A suggested link to another memory."""

    target_id: str = Field(..., description="Target memory ID")
    target_summary: str = Field(..., description="Target memory summary")
    similarity: float = Field(..., description="Similarity score (0-1)")
    suggested_relation: RelationType = Field(
        default=RelationType.RELATED, description="Suggested relation type"
    )
    reason: str = Field(..., description="Why this link is suggested")


class KnowledgeInsight(BaseModel):
    """An insight about knowledge quality improvement."""

    insight_type: str = Field(
        ..., description="Type: duplicate, contradiction, update_suggested, etc."
    )
    message: str = Field(..., description="Human-readable description")
    related_memory_id: str | None = Field(
        None, description="Related memory ID if applicable"
    )
    related_memory_summary: str | None = Field(
        None, description="Related memory summary"
    )
    confidence: float = Field(..., description="Confidence score (0-1)")
    suggested_action: str | None = Field(None, description="Suggested action to take")


class KnowledgeHealthIssue(BaseModel):
    """An issue found in the knowledge base."""

    issue_type: str = Field(
        ..., description="Type: orphan, stale, unlinked, duplicate_cluster, etc."
    )
    severity: str = Field(..., description="low, medium, high")
    message: str = Field(..., description="Human-readable description")
    affected_memory_ids: list[str] = Field(
        default_factory=list, description="Affected memory IDs"
    )
    suggested_action: str = Field(..., description="Suggested action to resolve")


# =============================================================================
# Result Models
# =============================================================================


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
    stats: dict = Field(default_factory=dict, description="Additional statistics")
