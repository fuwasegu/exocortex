"""Enumeration types for Exocortex domain models."""

from enum import Enum


class MemoryType(str, Enum):
    """Type of memory stored in Exocortex."""

    INSIGHT = "insight"  # General insights and learnings
    SUCCESS = "success"  # Successful solutions
    FAILURE = "failure"  # Failures and their causes
    DECISION = "decision"  # Technical decisions and reasoning
    NOTE = "note"  # General notes


class RelationType(str, Enum):
    """Type of relationship between memories.

    Basic relationships:
        RELATED: Generally related memories
        SUPERSEDES: This memory updates/replaces the target
        CONTRADICTS: This memory contradicts the target
        EXTENDS: This memory extends/elaborates the target
        DEPENDS_ON: This memory depends on the target

    Temporal reasoning relationships (Phase 2.3):
        EVOLVED_FROM: This memory evolved from an older version/design
        REJECTED_BECAUSE: This memory was rejected in favor of another approach
        CAUSED_BY: This memory (e.g., bug) was caused by the target (e.g., change)
    """

    # Basic relationships
    RELATED = "related"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    DEPENDS_ON = "depends_on"

    # Temporal reasoning relationships
    EVOLVED_FROM = "evolved_from"
    REJECTED_BECAUSE = "rejected_because"
    CAUSED_BY = "caused_by"  # This memory depends on the target
