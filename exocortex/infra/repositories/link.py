"""Link (relationship) operations."""

from __future__ import annotations

import logging

from ...domain.exceptions import DuplicateLinkError, MemoryNotFoundError, SelfLinkError
from ...domain.models import MemoryLink, RelationType

logger = logging.getLogger(__name__)


class LinkRepositoryMixin:
    """Mixin providing link (relationship) operations.

    Requires BaseRepositoryMixin to be mixed in.
    """

    def create_link(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType = RelationType.RELATED,
        reason: str | None = None,
    ) -> MemoryLink:
        """Create a link between two memories."""
        # Prevent self-links
        if source_id == target_id:
            raise SelfLinkError(source_id)

        # Verify both memories exist
        source = self.get_by_id(source_id)
        if not source:
            raise MemoryNotFoundError(source_id)

        target = self.get_by_id(target_id)
        if not target:
            raise MemoryNotFoundError(target_id)

        # Check if link already exists
        existing = self._execute_read(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if existing.has_next():
            raise DuplicateLinkError(source_id, target_id)

        # Create the link
        if reason:
            self._execute_write(
                """
                MATCH (s:Memory {id: $source_id})
                MATCH (t:Memory {id: $target_id})
                CREATE (s)-[:RELATED_TO {relation_type: $relation_type, reason: $reason}]->(t)
                """,
                parameters={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type.value,
                    "reason": reason,
                },
            )
        else:
            self._execute_write(
                """
                MATCH (s:Memory {id: $source_id})
                MATCH (t:Memory {id: $target_id})
                CREATE (s)-[:RELATED_TO {relation_type: $relation_type}]->(t)
                """,
                parameters={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type.value,
                },
            )

        return MemoryLink(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            reason=reason,
        )

    def get_links(self, memory_id: str) -> list[MemoryLink]:
        """Get all outgoing links from a memory."""
        result = self._execute_read(
            """
            MATCH (s:Memory {id: $id})-[r:RELATED_TO]->(t:Memory)
            RETURN t.id, r.relation_type, r.reason
            """,
            parameters={"id": memory_id},
        )

        links = []
        while result.has_next():
            row = result.get_next()
            links.append(
                MemoryLink(
                    source_id=memory_id,
                    target_id=row[0],
                    relation_type=RelationType(row[1])
                    if row[1]
                    else RelationType.RELATED,
                    reason=row[2],
                )
            )

        return links

    def delete_link(self, source_id: str, target_id: str) -> bool:
        """Delete a link between two memories."""
        # Check if link exists
        existing = self._execute_read(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not existing.has_next():
            return False

        # Delete the link
        self._execute_write(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            DELETE r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        return True
