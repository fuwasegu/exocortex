"""Repository pattern implementation for data access.

This module provides a modular repository architecture using mixins:
- BaseRepositoryMixin: Common database operations
- RowMapperMixin: Row-to-model conversion
- MemoryRepositoryMixin: Memory CRUD operations
- SearchRepositoryMixin: Search and retrieval
- LinkRepositoryMixin: Link/relationship operations
- PatternRepositoryMixin: Pattern abstraction
- StatsRepositoryMixin: Statistics and analysis

The MemoryRepository class combines all mixins into a single facade.
"""

from __future__ import annotations

from .base import BaseRepositoryMixin
from .link import LinkRepositoryMixin
from .memory import MemoryRepositoryMixin
from .pattern import PatternRepositoryMixin
from .row_mapper import RowMapperMixin
from .search import SearchRepositoryMixin
from .stats import StatsRepositoryMixin


class MemoryRepository(
    BaseRepositoryMixin,
    RowMapperMixin,
    MemoryRepositoryMixin,
    SearchRepositoryMixin,
    LinkRepositoryMixin,
    PatternRepositoryMixin,
    StatsRepositoryMixin,
):
    """Unified repository combining all data access operations.

    This class serves as a facade that combines specialized mixins:
    - Base: Database connection management
    - RowMapper: Convert DB rows to domain models
    - Memory: CRUD for memories
    - Search: Similarity search and exploration
    - Link: Memory relationships
    - Pattern: Pattern abstraction
    - Stats: Statistics and analysis
    """

    pass


__all__ = [
    "MemoryRepository",
    # Expose mixins for testing or extension
    "BaseRepositoryMixin",
    "RowMapperMixin",
    "MemoryRepositoryMixin",
    "SearchRepositoryMixin",
    "LinkRepositoryMixin",
    "PatternRepositoryMixin",
    "StatsRepositoryMixin",
]
