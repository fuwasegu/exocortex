"""Pattern abstraction operations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ...domain.models import Pattern

logger = logging.getLogger(__name__)


class PatternRepositoryMixin:
    """Mixin providing pattern abstraction operations.

    Requires BaseRepositoryMixin to be mixed in.
    """

    def create_pattern(
        self,
        content: str,
        source_memory_ids: list[str],
        tags: list[str] | None = None,
    ) -> Pattern:
        """Create a new pattern abstracted from memories."""
        pattern_id = str(uuid.uuid4())
        embedding = self._embedding_engine.embed(content)
        now = datetime.now(timezone.utc)

        # Create Pattern node
        self._execute_write(
            """
            CREATE (p:Pattern {
                id: $id,
                content: $content,
                embedding: $embedding,
                instance_count: $instance_count,
                created_at: $created_at
            })
            """,
            parameters={
                "id": pattern_id,
                "content": content,
                "embedding": embedding,
                "instance_count": len(source_memory_ids),
                "created_at": now,
            },
        )

        # Create tags
        if tags:
            for tag in tags:
                normalized_tag = tag.lower().strip()
                if not normalized_tag:
                    continue
                self._execute_write(
                    """
                    MERGE (t:Tag {name: $tag_name})
                    WITH t
                    MATCH (p:Pattern {id: $pattern_id})
                    CREATE (p)-[:TAGGED_WITH]->(t)
                    """,
                    parameters={"tag_name": normalized_tag, "pattern_id": pattern_id},
                )

        # Link source memories to pattern
        for memory_id in source_memory_ids:
            self._execute_write(
                """
                MATCH (m:Memory {id: $memory_id})
                MATCH (p:Pattern {id: $pattern_id})
                CREATE (m)-[:INSTANCE_OF]->(p)
                """,
                parameters={"memory_id": memory_id, "pattern_id": pattern_id},
            )

        return Pattern(
            id=pattern_id,
            content=content,
            instance_count=len(source_memory_ids),
            tags=tags or [],
            created_at=now,
        )

    def link_memory_to_pattern(self, memory_id: str, pattern_id: str) -> bool:
        """Link a memory as an instance of a pattern."""
        # Verify memory exists
        memory_check = self._execute_read(
            "MATCH (m:Memory {id: $id}) RETURN m.id",
            parameters={"id": memory_id},
        )
        if not memory_check.has_next():
            return False

        # Verify pattern exists
        pattern_check = self._execute_read(
            "MATCH (p:Pattern {id: $id}) RETURN p.id",
            parameters={"id": pattern_id},
        )
        if not pattern_check.has_next():
            return False

        # Check if link already exists
        existing_link = self._execute_read(
            """
            MATCH (m:Memory {id: $memory_id})-[:INSTANCE_OF]->(p:Pattern {id: $pattern_id})
            RETURN m.id
            """,
            parameters={"memory_id": memory_id, "pattern_id": pattern_id},
        )
        if existing_link.has_next():
            return True  # Already linked

        # Create link
        self._execute_write(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (p:Pattern {id: $pattern_id})
            CREATE (m)-[:INSTANCE_OF]->(p)
            """,
            parameters={"memory_id": memory_id, "pattern_id": pattern_id},
        )

        # Update instance count
        self._execute_write(
            """
            MATCH (p:Pattern {id: $pattern_id})
            SET p.instance_count = p.instance_count + 1
            """,
            parameters={"pattern_id": pattern_id},
        )

        return True

    def search_similar_patterns(
        self,
        query_embedding: list[float],
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[tuple[Pattern, float]]:
        """Search patterns by embedding similarity."""
        result = self._execute_read(
            """
            MATCH (p:Pattern)
            OPTIONAL MATCH (p)-[:TAGGED_WITH]->(t:Tag)
            RETURN p.id, p.content, p.embedding, p.instance_count, p.created_at,
                   collect(t.name) as tags
            """
        )

        patterns_with_scores = []
        while result.has_next():
            row = result.get_next()
            embedding = row[2]
            if embedding:
                similarity = self.compute_similarity(query_embedding, embedding)
                if similarity >= threshold:
                    tags = [t for t in row[5] if t] if row[5] else []
                    pattern = Pattern(
                        id=row[0],
                        content=row[1],
                        instance_count=row[3] or 0,
                        tags=tags,
                        created_at=row[4],
                    )
                    patterns_with_scores.append((pattern, similarity))

        patterns_with_scores.sort(key=lambda x: x[1], reverse=True)
        return patterns_with_scores[:limit]

    def get_pattern_by_id(self, pattern_id: str) -> Pattern | None:
        """Get a pattern by ID."""
        result = self._execute_read(
            """
            MATCH (p:Pattern {id: $id})
            OPTIONAL MATCH (p)-[:TAGGED_WITH]->(t:Tag)
            RETURN p.id, p.content, p.instance_count, p.created_at,
                   collect(t.name) as tags
            """,
            parameters={"id": pattern_id},
        )

        if not result.has_next():
            return None

        row = result.get_next()
        tags = [t for t in row[4] if t] if row[4] else []
        return Pattern(
            id=row[0],
            content=row[1],
            instance_count=row[2] or 0,
            tags=tags,
            created_at=row[3],
        )
