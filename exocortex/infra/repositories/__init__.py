"""Repository pattern implementation using Mixin-based composition.

This package provides a modular repository for memory data access:
- base.py: Common functionality (connection, row mapping)
- memory_crud.py: Create, Read, Update, Delete operations
- search.py: Vector search with hybrid scoring
- link.py: Memory relationships and graph exploration
- stats.py: Statistics and health analysis
- pattern.py: Pattern abstraction operations

The MemoryRepository class combines all mixins into a single facade.
"""

from __future__ import annotations

import logging

from ..database import DatabaseConnection, SmartDatabaseManager
from ..embeddings import EmbeddingEngine
from .base import BaseRepositoryMixin
from .link import LinkMixin
from .memory_crud import MemoryCrudMixin
from .pattern import PatternMixin
from .search import SearchMixin
from .stats import StatsMixin

logger = logging.getLogger(__name__)


class MemoryRepository(
    MemoryCrudMixin,
    SearchMixin,
    LinkMixin,
    StatsMixin,
    PatternMixin,
    BaseRepositoryMixin,
):
    """Repository for memory data access operations.

    Uses Mixin composition to combine functionality from multiple modules:
    - MemoryCrudMixin: create, get, update, delete, touch
    - SearchMixin: search_by_similarity, list_memories, hybrid scoring
    - LinkMixin: create_link, get_links, explore_related
    - StatsMixin: get_stats, orphans, stale memories
    - PatternMixin: create_pattern, link_memory_to_pattern

    All mixins share common methods from BaseRepositoryMixin.
    """

    def __init__(
        self,
        db_manager: SmartDatabaseManager | DatabaseConnection,
        embedding_engine: EmbeddingEngine,
        max_summary_length: int = 200,
    ) -> None:
        """Initialize the repository.

        Args:
            db_manager: Smart database manager or legacy database connection.
            embedding_engine: Embedding engine for vector operations.
            max_summary_length: Maximum length for summaries.
        """
        # Initialize base attributes
        self._init_base(db_manager, embedding_engine, max_summary_length)


__all__ = ["MemoryRepository"]
