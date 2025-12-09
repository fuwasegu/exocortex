"""Pattern/Abstraction models (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Pattern(BaseModel):
    """An abstract pattern/rule extracted from concrete memories.

    Patterns represent generalized insights discovered by analyzing
    clusters of similar memories. They form a higher level of abstraction
    in the knowledge hierarchy.

    Examples:
    - "Always use connection pooling for database connections"
    - "Prefer composition over inheritance in TypeScript"
    - "Check environment variables before deployment"
    """

    id: str = Field(..., description="Unique identifier (UUID)")
    content: str = Field(
        ..., description="Full description of the pattern/rule (Markdown)"
    )
    summary: str = Field(default="", description="Brief summary for search results")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0). Higher = more instances confirm this pattern",
    )
    instance_count: int = Field(
        default=1, description="Number of memories that exemplify this pattern"
    )
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")


class PatternInstance(BaseModel):
    """A link between a Memory and a Pattern it exemplifies."""

    memory_id: str = Field(..., description="Memory ID (instance)")
    pattern_id: str = Field(..., description="Pattern ID (abstract rule)")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How strongly this memory exemplifies the pattern",
    )
    created_at: datetime = Field(..., description="When the link was created")


class PatternWithInstances(Pattern):
    """A Pattern with its associated memory instances."""

    # Use Any at runtime, but type checkers see MemoryWithContext
    instances: list[Any] = Field(
        default_factory=list, description="Memories that exemplify this pattern"
    )
