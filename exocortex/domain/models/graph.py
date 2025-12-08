"""Graph node models for Context and Tag."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Context(BaseModel):
    """A context (project/situation) in Exocortex."""

    name: str = Field(..., description="Context name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")


class Tag(BaseModel):
    """A tag in Exocortex."""

    name: str = Field(..., description="Tag name (primary key)")
    created_at: datetime = Field(..., description="Creation timestamp")

