"""Core memory domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import MemoryType, RelationType


class Memory(BaseModel):
    """A memory stored in Exocortex.

    Includes Memory Dynamics fields for tracking recency and frequency,
    enabling smart recall scoring based on temporal and access patterns.
    """

    id: str = Field(..., description="Unique identifier (UUID)")
    content: str = Field(..., description="Full content of the memory (Markdown)")
    summary: str = Field(..., description="Brief summary for search results")
    memory_type: MemoryType = Field(
        default=MemoryType.INSIGHT, description="Type of memory"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # Memory Dynamics fields (Phase 1)
    last_accessed_at: datetime | None = Field(
        default=None, description="Last time this memory was accessed/recalled"
    )
    access_count: int = Field(
        default=1, description="Number of times this memory has been accessed"
    )
    decay_rate: float = Field(
        default=0.1,
        description="Memory decay rate (0.0-1.0). Higher = faster forgetting",
    )
    # Frustration Indexing fields (Phase 2.0 - Somatic Marker Hypothesis)
    frustration_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Emotional intensity score (0.0=calm, 1.0=extremely frustrated)",
    )
    time_cost_hours: float | None = Field(
        default=None,
        description="Estimated time spent on this problem (hours)",
    )


class MemoryLink(BaseModel):
    """A link between two memories."""

    source_id: str | None = Field(None, description="Source memory ID")
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
