"""Knowledge health and insight models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import RelationType


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

