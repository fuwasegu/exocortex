"""Data models for Exocortex."""

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


class MemoryWithContext(Memory):
    """A memory with its associated context and tags."""

    context: str | None = Field(None, description="Associated context/project name")
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    similarity: float | None = Field(
        None, description="Similarity score (for search results)"
    )


class Context(BaseModel):
    """A context (project/situation) in Exocortex."""

    name: str = Field(..., description="Context name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")


class Tag(BaseModel):
    """A tag in Exocortex."""

    name: str = Field(..., description="Tag name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")


class StoreMemoryInput(BaseModel):
    """Input for store_memory tool."""

    content: str = Field(..., description="Content to store")
    context_name: str = Field(..., description="Project or situation name")
    tags: list[str] = Field(..., description="Related keywords/tags")
    memory_type: MemoryType = Field(
        default=MemoryType.INSIGHT, description="Type of memory"
    )


class StoreMemoryResult(BaseModel):
    """Result of store_memory tool."""

    success: bool
    memory_id: str
    summary: str


class RecallMemoriesInput(BaseModel):
    """Input for recall_memories tool."""

    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, ge=1, le=20, description="Number of results")
    context_filter: str | None = Field(None, description="Filter by context")
    tag_filter: list[str] | None = Field(None, description="Filter by tags")
    type_filter: MemoryType | None = Field(None, description="Filter by memory type")


class RecallMemoriesResult(BaseModel):
    """Result of recall_memories tool."""

    memories: list[MemoryWithContext]
    total_found: int


class ListMemoriesInput(BaseModel):
    """Input for list_memories tool."""

    limit: int = Field(default=20, ge=1, le=100, description="Number of results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    context_filter: str | None = Field(None, description="Filter by context")
    tag_filter: list[str] | None = Field(None, description="Filter by tags")
    type_filter: MemoryType | None = Field(None, description="Filter by memory type")


class ListMemoriesResult(BaseModel):
    """Result of list_memories tool."""

    memories: list[MemoryWithContext]
    total_count: int
    has_more: bool


class GetMemoryResult(BaseModel):
    """Result of get_memory tool."""

    memory: MemoryWithContext | None


class DeleteMemoryResult(BaseModel):
    """Result of delete_memory tool."""

    success: bool
    deleted_id: str


class MemoryStats(BaseModel):
    """Statistics about stored memories."""

    total_memories: int
    memories_by_type: dict[str, int]
    total_contexts: int
    total_tags: int
    top_tags: list[dict[str, Any]]

