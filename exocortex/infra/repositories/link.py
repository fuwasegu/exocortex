"""Link and graph exploration operations.

This module handles memory-to-memory relationships and graph traversal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ...domain.exceptions import (
    DuplicateLinkError,
    MemoryNotFoundError,
    SelfLinkError,
)
from ...domain.models import (
    MemoryLink,
    MemoryType,
    MemoryWithContext,
    RelationType,
)
from ..queries import MemoryQueryBuilder
from .base import BaseRepositoryMixin

logger = logging.getLogger(__name__)


class LinkMixin(BaseRepositoryMixin):
    """Mixin for link and graph exploration operations."""

    # =========================================================================
    # Create Link
    # =========================================================================

    def create_link(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        reason: str | None = None,
    ) -> None:
        """Create a link between two memories.

        Args:
            source_id: Source memory ID.
            target_id: Target memory ID.
            relation_type: Type of relationship.
            reason: Optional reason for the link.

        Raises:
            SelfLinkError: If source and target are the same.
            MemoryNotFoundError: If one or both memories don't exist.
            DuplicateLinkError: If link already exists.
        """
        if source_id == target_id:
            raise SelfLinkError(source_id)

        # Check both memories exist
        result = self._execute_read(
            """
            MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
            RETURN s.id, t.id
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            raise MemoryNotFoundError(f"{source_id} or {target_id}")

        # Check if link already exists
        result = self._execute_read(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r.relation_type
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if result.has_next():
            existing_type = result.get_next()[0]
            raise DuplicateLinkError(source_id, target_id, existing_type)

        now = datetime.now(timezone.utc)

        # Create the relationship
        self._execute_write(
            """
            MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
            CREATE (s)-[:RELATED_TO {
                relation_type: $relation_type,
                reason: $reason,
                created_at: $created_at
            }]->(t)
            """,
            parameters={
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type.value,
                "reason": reason or "",
                "created_at": now,
            },
        )

        self._release_write_lock()

        logger.info(f"Linked memory {source_id} -> {target_id} ({relation_type.value})")

    # =========================================================================
    # Get Links
    # =========================================================================

    def get_links(self, memory_id: str) -> list[MemoryLink]:
        """Get all outgoing links from a memory."""
        result = self._execute_read(
            """
            MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(t:Memory)
            RETURN t.id, t.summary, r.relation_type, r.reason, r.created_at
            """,
            parameters={"id": memory_id},
        )

        links: list[MemoryLink] = []
        while result.has_next():
            row = result.get_next()
            links.append(
                MemoryLink(
                    target_id=row[0],
                    target_summary=row[1],
                    relation_type=RelationType(row[2]),
                    reason=row[3] if row[3] else None,
                    created_at=row[4],
                )
            )

        return links

    # =========================================================================
    # Delete Link
    # =========================================================================

    def delete_link(self, source_id: str, target_id: str) -> bool:
        """Delete a link between two memories."""
        result = self._execute_read(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            return False

        self._execute_write(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            DELETE r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        self._release_write_lock()

        logger.info(f"Unlinked memory {source_id} -> {target_id}")
        return True

    # =========================================================================
    # Graph Exploration
    # =========================================================================

    def explore_related(
        self,
        memory_id: str,
        include_tag_siblings: bool = True,
        include_context_siblings: bool = True,
        max_per_category: int = 5,
    ) -> dict[str, list[MemoryWithContext]]:
        """Explore memories related to a given memory."""
        result_dict: dict[str, list[MemoryWithContext]] = {
            "linked": [],
            "by_tag": [],
            "by_context": [],
        }

        # Get directly linked memories
        result = self._execute_read(
            MemoryQueryBuilder.explore_linked(),
            parameters={"id": memory_id, "limit": max_per_category},
        )

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[12] if t]
            memory = MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                last_accessed_at=row[6],
                access_count=row[7] if row[7] is not None else 1,
                decay_rate=row[8] if row[8] is not None else 0.1,
                frustration_score=row[9] if row[9] is not None else 0.0,
                time_cost_hours=row[10],
                context=row[11],
                tags=tags,
                related_memories=[
                    MemoryLink(
                        target_id=memory_id,
                        relation_type=RelationType(row[13]),
                        reason=row[14] if row[14] else None,
                    )
                ],
            )
            result_dict["linked"].append(memory)

        # Get tag siblings
        if include_tag_siblings:
            result = self._execute_read(
                MemoryQueryBuilder.explore_tag_siblings(),
                parameters={"id": memory_id, "limit": max_per_category},
            )

            seen_ids = {m.id for m in result_dict["linked"]}
            while result.has_next():
                row = result.get_next()
                if row[0] in seen_ids:
                    continue
                result_dict["by_tag"].append(self._row_to_memory(row))
                seen_ids.add(row[0])

        # Get context siblings
        if include_context_siblings:
            result = self._execute_read(
                MemoryQueryBuilder.explore_context_siblings(),
                parameters={"id": memory_id, "limit": max_per_category},
            )

            seen_ids = {m.id for m in result_dict["linked"]}
            seen_ids.update(m.id for m in result_dict["by_tag"])
            while result.has_next():
                row = result.get_next()
                if row[0] in seen_ids:
                    continue
                result_dict["by_context"].append(self._row_to_memory(row))

        return result_dict
