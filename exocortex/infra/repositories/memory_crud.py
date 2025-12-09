"""Memory CRUD (Create, Read, Update, Delete) operations.

This module handles basic memory lifecycle operations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ...domain.models import MemoryType, MemoryWithContext
from ..queries import MemoryQueryBuilder
from .base import BaseRepositoryMixin

logger = logging.getLogger(__name__)


class MemoryCrudMixin(BaseRepositoryMixin):
    """Mixin for memory CRUD operations."""

    # =========================================================================
    # Create Operations
    # =========================================================================

    def create_memory(
        self,
        content: str,
        context_name: str,
        tags: list[str],
        memory_type: MemoryType,
        frustration_score: float = 0.0,
        time_cost_hours: float | None = None,
    ) -> tuple[str, str, list[float]]:
        """Create a new memory in the database.

        Args:
            content: Memory content.
            context_name: Context/project name.
            tags: List of tags.
            memory_type: Type of memory.
            frustration_score: Emotional intensity score (0.0-1.0).
            time_cost_hours: Estimated time spent on this problem.

        Returns:
            Tuple of (memory_id, summary, embedding).
        """
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        summary = self._generate_summary(content)
        embedding = self._embedding_engine.embed(content)

        # Create memory node with dynamics fields
        self._execute_write(
            """
            CREATE (m:Memory {
                id: $id,
                content: $content,
                summary: $summary,
                embedding: $embedding,
                memory_type: $memory_type,
                created_at: $created_at,
                updated_at: $updated_at,
                last_accessed_at: $last_accessed_at,
                access_count: $access_count,
                decay_rate: $decay_rate,
                frustration_score: $frustration_score,
                time_cost_hours: $time_cost_hours
            })
            """,
            parameters={
                "id": memory_id,
                "content": content,
                "summary": summary,
                "embedding": embedding,
                "memory_type": memory_type.value,
                "created_at": now,
                "updated_at": now,
                "last_accessed_at": now,
                "access_count": 1,
                "decay_rate": 0.1,
                "frustration_score": frustration_score,
                "time_cost_hours": time_cost_hours,
            },
        )

        # Create or get context
        self._execute_write(
            """
            MERGE (c:Context {name: $name})
            ON CREATE SET c.created_at = $created_at
            """,
            parameters={"name": context_name, "created_at": now},
        )

        # Create relationship to context
        self._execute_write(
            """
            MATCH (m:Memory {id: $memory_id}), (c:Context {name: $context_name})
            CREATE (m)-[:ORIGINATED_IN]->(c)
            """,
            parameters={"memory_id": memory_id, "context_name": context_name},
        )

        # Create tags and relationships
        for tag in tags:
            tag_normalized = tag.strip().lower()
            if not tag_normalized:
                continue

            self._execute_write(
                """
                MERGE (t:Tag {name: $name})
                ON CREATE SET t.created_at = $created_at
                """,
                parameters={"name": tag_normalized, "created_at": now},
            )

            self._execute_write(
                """
                MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"memory_id": memory_id, "tag_name": tag_normalized},
            )

        self._release_write_lock()

        logger.info(f"Created memory {memory_id} with {len(tags)} tags")
        return memory_id, summary, embedding

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_by_id(self, memory_id: str) -> MemoryWithContext | None:
        """Get a memory by ID."""
        result = self._execute_read(
            MemoryQueryBuilder.get_by_id(),
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return None

        return self._row_to_memory(result.get_next())

    # =========================================================================
    # Update Operations
    # =========================================================================

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        memory_type: MemoryType | None = None,
    ) -> tuple[bool, list[str], str]:
        """Update an existing memory.

        Note: Due to KùzuDB vector index constraints, updating content
        requires delete-and-recreate of the memory node.

        Returns:
            Tuple of (success, changes, summary).
        """
        # Get existing memory info including tags
        result = self._execute_read(
            """
            MATCH (m:Memory {id: $id})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at, c.name as context,
                   collect(t.name) as tags
            """,
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return False, [], ""

        row = result.get_next()
        current_summary = row[2]
        current_type = row[3]
        created_at = row[4]
        context_name = row[6]
        existing_tags = [t for t in row[7] if t] if row[7] else []

        changes: list[str] = []
        now = datetime.now(timezone.utc)
        summary = current_summary

        # Determine which tags to use
        tags_to_apply = tags if tags is not None else existing_tags
        tags_changed = tags is not None

        # If content changes, we need to delete and recreate due to vector index
        if content is not None:
            embedding = self._embedding_engine.embed(content)
            summary = self._generate_summary(content)
            new_type = memory_type.value if memory_type else current_type

            # Get existing RELATED_TO links (both directions)
            outgoing_links = []
            result = self._execute_read(
                """
                MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(t:Memory)
                RETURN t.id, r.relation_type, r.reason, r.created_at
                """,
                parameters={"id": memory_id},
            )
            while result.has_next():
                outgoing_links.append(result.get_next())

            incoming_links = []
            result = self._execute_read(
                """
                MATCH (s:Memory)-[r:RELATED_TO]->(m:Memory {id: $id})
                RETURN s.id, r.relation_type, r.reason, r.created_at
                """,
                parameters={"id": memory_id},
            )
            while result.has_next():
                incoming_links.append(result.get_next())

            # Delete the old memory node and all its relationships
            for rel_query in [
                "MATCH (m:Memory {id: $id})-[r:ORIGINATED_IN]->(:Context) DELETE r",
                "MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag) DELETE r",
                "MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(:Memory) DELETE r",
                "MATCH (:Memory)-[r:RELATED_TO]->(m:Memory {id: $id}) DELETE r",
                "MATCH (m:Memory {id: $id}) DELETE m",
            ]:
                self._execute_write(rel_query, parameters={"id": memory_id})

            # Recreate memory with new content
            self._execute_write(
                """
                CREATE (m:Memory {
                    id: $id,
                    content: $content,
                    summary: $summary,
                    embedding: $embedding,
                    memory_type: $memory_type,
                    created_at: $created_at,
                    updated_at: $updated_at
                })
                """,
                parameters={
                    "id": memory_id,
                    "content": content,
                    "summary": summary,
                    "embedding": embedding,
                    "memory_type": new_type,
                    "created_at": created_at,
                    "updated_at": now,
                },
            )

            # Re-create context relationship
            if context_name:
                self._execute_write(
                    """
                    MATCH (m:Memory {id: $memory_id}), (c:Context {name: $context_name})
                    CREATE (m)-[:ORIGINATED_IN]->(c)
                    """,
                    parameters={"memory_id": memory_id, "context_name": context_name},
                )

            # Re-create tags (either new or existing)
            self._create_tag_relationships(memory_id, tags_to_apply, now)

            # Re-create RELATED_TO links
            for link in outgoing_links:
                self._execute_write(
                    """
                    MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
                    CREATE (s)-[:RELATED_TO {
                        relation_type: $relation_type,
                        reason: $reason,
                        created_at: $link_created_at
                    }]->(t)
                    """,
                    parameters={
                        "source_id": memory_id,
                        "target_id": link[0],
                        "relation_type": link[1],
                        "reason": link[2] or "",
                        "link_created_at": link[3],
                    },
                )

            for link in incoming_links:
                self._execute_write(
                    """
                    MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
                    CREATE (s)-[:RELATED_TO {
                        relation_type: $relation_type,
                        reason: $reason,
                        created_at: $link_created_at
                    }]->(t)
                    """,
                    parameters={
                        "source_id": link[0],
                        "target_id": memory_id,
                        "relation_type": link[1],
                        "reason": link[2] or "",
                        "link_created_at": link[3],
                    },
                )

            changes.append("content")
            if memory_type is not None:
                changes.append("memory_type")
            if tags_changed:
                changes.append("tags")

        else:
            # No content change - can update in place
            if memory_type is not None:
                self._execute_write(
                    """
                    MATCH (m:Memory {id: $id})
                    SET m.memory_type = $memory_type,
                        m.updated_at = $updated_at
                    """,
                    parameters={
                        "id": memory_id,
                        "memory_type": memory_type.value,
                        "updated_at": now,
                    },
                )
                changes.append("memory_type")

            if tags_changed:
                # Delete existing tag relationships
                self._execute_write(
                    """
                    MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag)
                    DELETE r
                    """,
                    parameters={"id": memory_id},
                )

                # Create new tag relationships
                self._create_tag_relationships(memory_id, tags_to_apply, now)
                changes.append("tags")

            # Update timestamp if only tags changed
            if changes and memory_type is None:
                self._execute_write(
                    """
                    MATCH (m:Memory {id: $id})
                    SET m.updated_at = $updated_at
                    """,
                    parameters={"id": memory_id, "updated_at": now},
                )

        self._release_write_lock()

        # Get updated summary if not already set
        if not summary:
            memory = self.get_by_id(memory_id)
            summary = memory.summary if memory else ""

        logger.info(f"Updated memory {memory_id}: {changes}")
        return True, changes, summary

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory and its relationships."""
        result = self._execute_read(
            "MATCH (m:Memory {id: $id}) RETURN m.id",
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return False

        # Delete relationships
        self._execute_write(
            "MATCH (m:Memory {id: $id})-[r:ORIGINATED_IN]->(:Context) DELETE r",
            parameters={"id": memory_id},
        )
        self._execute_write(
            "MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag) DELETE r",
            parameters={"id": memory_id},
        )
        self._execute_write(
            "MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(:Memory) DELETE r",
            parameters={"id": memory_id},
        )
        self._execute_write(
            "MATCH (:Memory)-[r:RELATED_TO]->(m:Memory {id: $id}) DELETE r",
            parameters={"id": memory_id},
        )

        # Delete node
        self._execute_write(
            "MATCH (m:Memory {id: $id}) DELETE m",
            parameters={"id": memory_id},
        )

        self._release_write_lock()

        logger.info(f"Deleted memory {memory_id}")
        return True

    # =========================================================================
    # Access Tracking
    # =========================================================================

    def touch_memory(self, memory_id: str) -> bool:
        """Update memory access metadata (last_accessed_at, access_count)."""
        now = datetime.now(timezone.utc)
        try:
            self._execute_write(
                """
                MATCH (m:Memory {id: $id})
                SET m.last_accessed_at = $now,
                    m.access_count = CASE
                        WHEN m.access_count IS NULL THEN 1
                        ELSE m.access_count + 1
                    END
                """,
                parameters={"id": memory_id, "now": now},
            )
            self._release_write_lock()
            logger.debug(f"Touched memory {memory_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to touch memory {memory_id}: {e}")
            return False

    def touch_memories(self, memory_ids: list[str]) -> int:
        """Batch update memory access metadata for multiple memories."""
        if not memory_ids:
            return 0

        now = datetime.now(timezone.utc)
        touched = 0
        for memory_id in memory_ids:
            try:
                self._execute_write(
                    """
                    MATCH (m:Memory {id: $id})
                    SET m.last_accessed_at = $now,
                        m.access_count = CASE
                            WHEN m.access_count IS NULL THEN 1
                            ELSE m.access_count + 1
                        END
                    """,
                    parameters={"id": memory_id, "now": now},
                )
                touched += 1
            except Exception as e:
                logger.warning(f"Failed to touch memory {memory_id}: {e}")

        self._release_write_lock()
        logger.debug(f"Touched {touched}/{len(memory_ids)} memories")
        return touched

