"""Memory CRUD operations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...domain.models import MemoryType, MemoryWithContext
from ..queries import MemoryQueryBuilder

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MemoryRepositoryMixin:
    """Mixin providing Memory CRUD operations.

    Requires BaseRepositoryMixin to be mixed in.
    """

    def create_memory(
        self,
        content: str,
        memory_type: MemoryType,
        context_name: str | None = None,
        tags: list[str] | None = None,
        frustration_score: float = 0.0,
        time_cost_hours: float | None = None,
    ) -> MemoryWithContext:
        """Create a new memory with embedding."""
        memory_id = str(uuid.uuid4())
        embedding = self._embedding_engine.embed(content)
        summary = self._generate_summary(content)
        now = datetime.now(timezone.utc)

        # Build time_cost_hours value for query
        time_cost_value = time_cost_hours if time_cost_hours is not None else "null"

        # Create Memory node with dynamics fields
        self._execute_write(
            f"""
            CREATE (m:Memory {{
                id: $id,
                content: $content,
                summary: $summary,
                embedding: $embedding,
                memory_type: $memory_type,
                created_at: $created_at,
                updated_at: $updated_at,
                last_accessed_at: $last_accessed_at,
                access_count: 1,
                decay_rate: 1.0,
                frustration_score: $frustration_score,
                time_cost_hours: {time_cost_value}
            }})
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
                "frustration_score": frustration_score,
            },
        )

        # Create or link to Context
        if context_name:
            self._execute_write(
                """
                MERGE (c:Context {name: $context_name})
                WITH c
                MATCH (m:Memory {id: $memory_id})
                CREATE (m)-[:ORIGINATED_IN]->(c)
                """,
                parameters={"context_name": context_name, "memory_id": memory_id},
            )

        # Create tags and relationships
        if tags:
            self._create_tag_relationships(memory_id, tags)

        return MemoryWithContext(
            id=memory_id,
            content=content,
            summary=summary,
            memory_type=memory_type,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            access_count=1,
            decay_rate=1.0,
            frustration_score=frustration_score,
            time_cost_hours=time_cost_hours,
            context=context_name,
            tags=tags or [],
        )

    def _create_tag_relationships(self, memory_id: str, tags: list[str]) -> None:
        """Create tag nodes and relationships."""
        for tag in tags:
            normalized_tag = tag.lower().strip()
            if not normalized_tag:
                continue
            self._execute_write(
                """
                MERGE (t:Tag {name: $tag_name})
                WITH t
                MATCH (m:Memory {id: $memory_id})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"tag_name": normalized_tag, "memory_id": memory_id},
            )

    def get_by_id(self, memory_id: str) -> MemoryWithContext | None:
        """Get a memory by ID."""
        result = self._execute_read(
            MemoryQueryBuilder.get_by_id(),
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return None

        return self._row_to_memory(result.get_next())

    def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: str | None = None,
    ) -> list[MemoryWithContext]:
        """List memories with pagination and filtering."""
        # Build WHERE clause
        conditions = []
        parameters: dict = {"limit": limit, "offset": offset}

        if context_filter:
            conditions.append("c.name = $context_filter")
            parameters["context_filter"] = context_filter

        if type_filter:
            conditions.append("m.memory_type = $type_filter")
            parameters["type_filter"] = type_filter

        # Tag filter requires a different approach (check if memory has all tags)
        if tag_filter:
            for i, tag in enumerate(tag_filter):
                param_name = f"tag_{i}"
                conditions.append(
                    f"EXISTS {{ MATCH (m)-[:TAGGED_WITH]->(t:Tag) WHERE t.name = ${param_name} }}"
                )
                parameters[param_name] = tag.lower()

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # Get memories with dynamics and frustration fields
        query = MemoryQueryBuilder.list_memories(where_clause)

        result = self._execute_read(query, parameters=parameters)

        memories = []
        while result.has_next():
            memories.append(self._row_to_memory(result.get_next()))

        return memories

    def touch_memory(self, memory_id: str) -> bool:
        """Update last_accessed_at and increment access_count for a memory.

        Returns True if the memory was found and updated.
        """
        now = datetime.now(timezone.utc)
        result = self._execute_write(
            """
            MATCH (m:Memory {id: $id})
            SET m.last_accessed_at = $now,
                m.access_count = m.access_count + 1
            RETURN m.id
            """,
            parameters={"id": memory_id, "now": now},
        )
        return result.has_next()

    def touch_memories(self, memory_ids: list[str]) -> int:
        """Update last_accessed_at and increment access_count for multiple memories.

        Returns the number of memories that were updated.
        """
        if not memory_ids:
            return 0

        now = datetime.now(timezone.utc)
        updated_count = 0

        # Update each memory individually
        # KùzuDB doesn't support IN clauses well, so we do this one by one
        for memory_id in memory_ids:
            result = self._execute_write(
                """
                MATCH (m:Memory {id: $id})
                SET m.last_accessed_at = $now,
                    m.access_count = m.access_count + 1
                RETURN m.id
                """,
                parameters={"id": memory_id, "now": now},
            )
            if result.has_next():
                updated_count += 1

        return updated_count

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        memory_type: MemoryType | None = None,
    ) -> MemoryWithContext | None:
        """Update an existing memory."""
        # First, get the existing memory to ensure it exists
        existing = self.get_by_id(memory_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        updates = ["m.updated_at = $updated_at"]
        parameters: dict = {"id": memory_id, "updated_at": now}

        # Handle content update
        if content is not None:
            embedding = self._embedding_engine.embed(content)
            summary = self._generate_summary(content)
            updates.extend(
                [
                    "m.content = $content",
                    "m.summary = $summary",
                    "m.embedding = $embedding",
                ]
            )
            parameters["content"] = content
            parameters["summary"] = summary
            parameters["embedding"] = embedding

        # Handle memory_type update
        if memory_type is not None:
            updates.append("m.memory_type = $memory_type")
            parameters["memory_type"] = memory_type.value

        # Execute the update
        self._execute_write(
            f"""
            MATCH (m:Memory {{id: $id}})
            SET {", ".join(updates)}
            """,
            parameters=parameters,
        )

        # Handle tags update
        if tags is not None:
            # Remove existing tag relationships
            self._execute_write(
                """
                MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag)
                DELETE r
                """,
                parameters={"id": memory_id},
            )
            # Create new tag relationships
            if tags:
                self._create_tag_relationships(memory_id, tags)

        return self.get_by_id(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory and its relationships."""
        # Check if memory exists
        existing = self.get_by_id(memory_id)
        if not existing:
            return False

        # Delete all relationships first
        self._execute_write(
            """
            MATCH (m:Memory {id: $id})-[r]-()
            DELETE r
            """,
            parameters={"id": memory_id},
        )

        # Delete the memory node
        self._execute_write(
            """
            MATCH (m:Memory {id: $id})
            DELETE m
            """,
            parameters={"id": memory_id},
        )

        return True
