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
    """Type of relationship between memories."""

    RELATED = "related"  # Generally related memories
    SUPERSEDES = "supersedes"  # This memory updates/replaces the target
    CONTRADICTS = "contradicts"  # This memory contradicts the target
    EXTENDS = "extends"  # This memory extends/elaborates the target
    DEPENDS_ON = "depends_on"  # This memory depends on the target

