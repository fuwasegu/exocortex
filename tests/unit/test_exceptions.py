"""Unit tests for domain exceptions."""

from __future__ import annotations

import pytest

from exocortex.domain.exceptions import (
    DatabaseError,
    DuplicateLinkError,
    ExocortexError,
    MemoryNotFoundError,
    SelfLinkError,
    ValidationError,
)


class TestExceptions:
    """Tests for custom exceptions."""

    def test_base_exception(self):
        """Test base ExocortexError."""
        with pytest.raises(ExocortexError):
            raise ExocortexError("Base error")

    def test_validation_error(self):
        """Test ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Content cannot be empty")

        assert "Content cannot be empty" in str(exc_info.value)

    def test_memory_not_found_error(self):
        """Test MemoryNotFoundError."""
        error = MemoryNotFoundError("abc-123")

        assert error.memory_id == "abc-123"
        assert "abc-123" in str(error)
        assert "not found" in str(error).lower()

    def test_duplicate_link_error(self):
        """Test DuplicateLinkError."""
        error = DuplicateLinkError(
            source_id="src-123",
            target_id="tgt-456",
            existing_type="extends",
        )

        assert error.source_id == "src-123"
        assert error.target_id == "tgt-456"
        assert error.existing_type == "extends"
        assert "already exists" in str(error).lower()

    def test_self_link_error(self):
        """Test SelfLinkError."""
        error = SelfLinkError("mem-123")

        assert error.memory_id == "mem-123"
        assert "itself" in str(error).lower()

    def test_database_error(self):
        """Test DatabaseError."""
        with pytest.raises(DatabaseError):
            raise DatabaseError("Connection failed")

    def test_exception_inheritance(self):
        """Test that all exceptions inherit from ExocortexError."""
        assert issubclass(ValidationError, ExocortexError)
        assert issubclass(MemoryNotFoundError, ExocortexError)
        assert issubclass(DuplicateLinkError, ExocortexError)
        assert issubclass(SelfLinkError, ExocortexError)
        assert issubclass(DatabaseError, ExocortexError)


