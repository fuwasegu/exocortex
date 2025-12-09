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

    def get_incoming_links(
        self, memory_id: str, relation_type: RelationType | None = None
    ) -> list[MemoryLink]:
        """Get all incoming links to a memory (links pointing TO this memory).

        This is useful for finding memories that supersede, contradict, or
        reference the given memory.

        Args:
            memory_id: The target memory ID.
            relation_type: Optional filter by relation type.

        Returns:
            List of MemoryLink objects representing incoming links.
            Note: source_id is stored in target_id field for compatibility.
        """
        if relation_type:
            query = """
                MATCH (s:Memory)-[r:RELATED_TO]->(t:Memory {id: $id})
                WHERE r.relation_type = $relation_type
                RETURN s.id, s.summary, r.relation_type, r.reason, r.created_at
            """
            params = {"id": memory_id, "relation_type": relation_type.value}
        else:
            query = """
                MATCH (s:Memory)-[r:RELATED_TO]->(t:Memory {id: $id})
                RETURN s.id, s.summary, r.relation_type, r.reason, r.created_at
            """
            params = {"id": memory_id}

        result = self._execute_read(query, parameters=params)

        links: list[MemoryLink] = []
        while result.has_next():
            row = result.get_next()
            # Note: We store source_id in target_id field for API compatibility
            # The caller should interpret this as "source memory that links to us"
            links.append(
                MemoryLink(
                    target_id=row[0],  # Actually the source memory ID
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

    # =========================================================================
    # Temporal Reasoning (Phase 2.3)
    # =========================================================================

    def _row_to_lineage_node(self, row: list, depth: int) -> dict:
        """Convert a database row to a lineage node dictionary.

        Row column order (must match RETURN clause in trace_lineage queries):
            0: id (memory ID)
            1: summary (memory summary)
            2: memory_type (type of memory)
            3: created_at (creation timestamp)
            4: relation_type (how this node relates to its parent)
            5: reason (why the relationship exists)
        """
        return {
            "id": row[0],
            "summary": row[1],
            "memory_type": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "depth": depth,
            "relation_type": row[4],
            "reason": row[5] if row[5] else None,
        }

    def trace_lineage(
        self,
        memory_id: str,
        direction: str = "backward",
        relation_types: list[str] | None = None,
        max_depth: int = 10,
    ) -> list[dict]:
        """Trace the lineage of a memory through temporal relationships.

        Follows relationships like EVOLVED_FROM, CAUSED_BY, REJECTED_BECAUSE
        to build a timeline of how decisions/code evolved.

        Uses BFS (Breadth-First Search) with a visited set to handle cycles safely.

        Args:
            memory_id: Starting memory ID.
            direction: "backward" (find ancestors) or "forward" (find descendants).
            relation_types: List of relation types to follow. Defaults to temporal types.
            max_depth: Maximum traversal depth to prevent infinite loops.

        Returns:
            List of lineage nodes, each containing:
            - id: Memory ID
            - summary: Memory summary
            - memory_type: Type of memory
            - created_at: Creation timestamp
            - depth: Distance from starting node
            - relation_type: How this node relates to its parent
            - reason: Why the relationship exists
        """
        if relation_types is None:
            # Default to temporal reasoning relationships
            relation_types = [
                "evolved_from",
                "caused_by",
                "rejected_because",
                "supersedes",
            ]

        # TODO: Performance optimization opportunity
        # KùzuDB may support variable-length path queries like:
        #   MATCH (m:Memory {id: $id})-[r:RELATED_TO*1..10]->(target:Memory)
        #   WHERE ALL(rel IN r WHERE rel.relation_type IN $types)
        # This could fetch all nodes in one query instead of N+1.
        # Current Python-side BFS is safer given KùzuDB's Cypher support level.

        # Use iterative BFS approach with multiple hops
        lineage: list[dict] = []
        visited: set[str] = {memory_id}  # Prevents cycles
        current_ids = [memory_id]
        depth = 0

        while current_ids and depth < max_depth:
            depth += 1
            next_ids = []

            for current_id in current_ids:
                # Query columns: id, summary, memory_type, created_at, relation_type, reason
                if direction == "backward":
                    query = """
                        MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(target:Memory)
                        WHERE r.relation_type IN $relation_types
                        RETURN target.id, target.summary, target.memory_type,
                               target.created_at, r.relation_type, r.reason
                        ORDER BY target.created_at DESC
                    """
                else:
                    query = """
                        MATCH (source:Memory)-[r:RELATED_TO]->(m:Memory {id: $id})
                        WHERE r.relation_type IN $relation_types
                        RETURN source.id, source.summary, source.memory_type,
                               source.created_at, r.relation_type, r.reason
                        ORDER BY source.created_at ASC
                    """

                result = self._execute_read(
                    query,
                    parameters={"id": current_id, "relation_types": relation_types},
                )

                while result.has_next():
                    row = result.get_next()
                    node_id = row[0]

                    # Skip already visited nodes (handles cycles)
                    if node_id not in visited:
                        visited.add(node_id)
                        next_ids.append(node_id)
                        lineage.append(self._row_to_lineage_node(row, depth))

            current_ids = next_ids

        # Sort by created_at for chronological order
        lineage.sort(
            key=lambda x: x["created_at"] if x["created_at"] else "",
            reverse=(direction == "backward"),
        )

        return lineage
