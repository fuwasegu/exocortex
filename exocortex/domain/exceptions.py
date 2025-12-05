"""Custom exceptions for Exocortex."""

from __future__ import annotations


class ExocortexError(Exception):
    """Base exception for Exocortex."""

    pass


class ValidationError(ExocortexError):
    """Raised when input validation fails."""

    pass


class MemoryNotFoundError(ExocortexError):
    """Raised when a memory is not found."""

    def __init__(self, memory_id: str) -> None:
        self.memory_id = memory_id
        super().__init__(f"Memory with ID '{memory_id}' not found")


class DuplicateLinkError(ExocortexError):
    """Raised when attempting to create a duplicate link."""

    def __init__(self, source_id: str, target_id: str, existing_type: str) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.existing_type = existing_type
        super().__init__(
            f"Link already exists from '{source_id}' to '{target_id}' "
            f"with relation type '{existing_type}'"
        )


class SelfLinkError(ExocortexError):
    """Raised when attempting to link a memory to itself."""

    def __init__(self, memory_id: str) -> None:
        self.memory_id = memory_id
        super().__init__(f"Cannot link memory '{memory_id}' to itself")


class DatabaseError(ExocortexError):
    """Raised when a database operation fails."""

    pass
