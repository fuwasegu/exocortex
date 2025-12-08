"""Row-to-model mapping utilities."""

from __future__ import annotations

import logging
from typing import Any

from ...domain.models import MemoryType, MemoryWithContext
from ..queries import MemoryQueryBuilder

logger = logging.getLogger(__name__)


class RowMapperMixin:
    """Mixin providing row-to-model mapping.

    Uses centralized column indices from MemoryQueryBuilder.
    """

    def _row_to_memory(self, row: list[Any]) -> MemoryWithContext:
        """Convert a database row to MemoryWithContext.

        Uses indices from MemoryQueryBuilder.Columns for consistent mapping.
        """
        cols = MemoryQueryBuilder.Columns

        # Handle tags - may be in different positions for different queries
        # Standard position is 12, but some queries have additional columns after
        tags_idx = cols.TAGS
        tags_raw = row[tags_idx] if len(row) > tags_idx else []
        tags = [t for t in tags_raw if t] if tags_raw else []

        # Handle frustration score and time_cost_hours
        frustration_score = row[cols.FRUSTRATION_SCORE]
        if frustration_score is None:
            frustration_score = 0.0

        time_cost_hours = row[cols.TIME_COST_HOURS]

        return MemoryWithContext(
            id=row[cols.ID],
            content=row[cols.CONTENT],
            summary=row[cols.SUMMARY],
            memory_type=MemoryType(row[cols.MEMORY_TYPE]),
            created_at=row[cols.CREATED_AT],
            updated_at=row[cols.UPDATED_AT],
            last_accessed_at=row[cols.LAST_ACCESSED_AT],
            access_count=row[cols.ACCESS_COUNT] or 1,
            decay_rate=row[cols.DECAY_RATE] or 1.0,
            frustration_score=frustration_score,
            time_cost_hours=time_cost_hours,
            context=row[cols.CONTEXT],
            tags=tags,
        )
