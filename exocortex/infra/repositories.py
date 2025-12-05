"""Repository pattern implementation for data access."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..domain.exceptions import (
    DuplicateLinkError,
    MemoryNotFoundError,
    SelfLinkError,
)
from ..domain.models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
)
from .database import DatabaseConnection
from .embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for memory data access operations."""

    def __init__(
        self,
        db: DatabaseConnection,
        embedding_engine: EmbeddingEngine,
        max_summary_length: int = 200,
    ) -> None:
        """Initialize the repository.

        Args:
            db: Database connection.
            embedding_engine: Embedding engine for vector operations.
            max_summary_length: Maximum length for summaries.
        """
        self._db = db
        self._embedding_engine = embedding_engine
        self._max_summary_length = max_summary_length

    def _generate_summary(self, content: str) -> str:
        """Generate a summary from content."""
        content = content.strip()
        if len(content) <= self._max_summary_length:
            return content

        truncated = content[: self._max_summary_length]
        last_space = truncated.rfind(" ")
        if last_space > self._max_summary_length * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    def _row_to_memory(
        self,
        row: tuple,
        include_content: bool = True,
        similarity: float | None = None,
        related_memories: list[MemoryLink] | None = None,
    ) -> MemoryWithContext:
        """Convert a database row to MemoryWithContext."""
        if include_content:
            # Full row: (id, content, summary, memory_type, created_at, updated_at, context, tags)
            tags = [t for t in row[7] if t] if row[7] else []
            return MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                context=row[6],
                tags=tags,
                similarity=similarity,
                related_memories=related_memories or [],
            )
        else:
            # Summary row: (id, summary, memory_type, created_at, updated_at, context, tags)
            tags = [t for t in row[6] if t] if row[6] else []
            return MemoryWithContext(
                id=row[0],
                content="",
                summary=row[1],
                memory_type=MemoryType(row[2]),
                created_at=row[3],
                updated_at=row[4],
                context=row[5],
                tags=tags,
                similarity=similarity,
                related_memories=related_memories or [],
            )

    # =========================================================================
    # Create Operations
    # =========================================================================

    def create_memory(
        self,
        content: str,
        context_name: str,
        tags: list[str],
        memory_type: MemoryType,
    ) -> tuple[str, str, list[float]]:
        """Create a new memory in the database.

        Args:
            content: Memory content.
            context_name: Context/project name.
            tags: List of tags.
            memory_type: Type of memory.

        Returns:
            Tuple of (memory_id, summary, embedding).
        """
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        summary = self._generate_summary(content)
        embedding = self._embedding_engine.embed(content)

        # Create memory node
        self._db.execute(
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
                "memory_type": memory_type.value,
                "created_at": now,
                "updated_at": now,
            },
        )

        # Create or get context
        self._db.execute(
            """
            MERGE (c:Context {name: $name})
            ON CREATE SET c.created_at = $created_at
            """,
            parameters={"name": context_name, "created_at": now},
        )

        # Create relationship to context
        self._db.execute(
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

            self._db.execute(
                """
                MERGE (t:Tag {name: $name})
                ON CREATE SET t.created_at = $created_at
                """,
                parameters={"name": tag_normalized, "created_at": now},
            )

            self._db.execute(
                """
                MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"memory_id": memory_id, "tag_name": tag_normalized},
            )

        logger.info(f"Created memory {memory_id} with {len(tags)} tags")
        return memory_id, summary, embedding

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
        result = self._db.execute(
            """
            MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
            RETURN s.id, t.id
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            raise MemoryNotFoundError(f"{source_id} or {target_id}")

        # Check if link already exists
        result = self._db.execute(
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
        self._db.execute(
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

        logger.info(f"Linked memory {source_id} -> {target_id} ({relation_type.value})")

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_by_id(self, memory_id: str) -> MemoryWithContext | None:
        """Get a memory by ID."""
        result = self._db.execute(
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
            return None

        return self._row_to_memory(result.get_next())

    def get_all_with_embeddings(self) -> list[tuple[str, str, list[float], str, str]]:
        """Get all memories with their embeddings.

        Returns:
            List of (id, summary, embedding, memory_type, context) tuples.
        """
        result = self._db.execute("""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            RETURN m.id, m.summary, m.embedding, m.memory_type, c.name as context
        """)

        memories = []
        while result.has_next():
            row = result.get_next()
            memories.append((row[0], row[1], row[2], row[3], row[4]))
        return memories

    def search_by_similarity(
        self,
        query: str,
        limit: int = 5,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
    ) -> tuple[list[MemoryWithContext], int]:
        """Search memories by semantic similarity.

        Args:
            query: Search query.
            limit: Maximum results.
            context_filter: Filter by context.
            tag_filter: Filter by tags.
            type_filter: Filter by type.

        Returns:
            Tuple of (memories, total_found).
        """
        query_embedding = self._embedding_engine.embed(query)

        result = self._db.execute("""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN m.id, m.content, m.summary, m.embedding, m.memory_type,
                   m.created_at, m.updated_at, c.name as context,
                   collect(t.name) as tags
        """)

        memories_with_scores: list[tuple[MemoryWithContext, float]] = []

        while result.has_next():
            row = result.get_next()
            memory_id = row[0]
            content = row[1]
            summary = row[2]
            embedding = row[3]
            memory_type = row[4]
            created_at = row[5]
            updated_at = row[6]
            context = row[7]
            tags = [t for t in row[8] if t]

            # Apply filters
            if context_filter and context != context_filter:
                continue
            if type_filter and memory_type != type_filter.value:
                continue
            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            similarity = self._embedding_engine.compute_similarity(
                query_embedding, embedding
            )

            memory = MemoryWithContext(
                id=memory_id,
                content=content,
                summary=summary,
                memory_type=MemoryType(memory_type),
                created_at=created_at,
                updated_at=updated_at,
                context=context,
                tags=tags,
                similarity=similarity,
            )

            memories_with_scores.append((memory, similarity))

        memories_with_scores.sort(key=lambda x: x[1], reverse=True)
        total_found = len(memories_with_scores)
        top_memories = [m for m, _ in memories_with_scores[:limit]]

        return top_memories, total_found

    def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
    ) -> tuple[list[MemoryWithContext], int, bool]:
        """List memories with pagination."""
        where_clauses = []
        params: dict[str, Any] = {}

        if context_filter:
            where_clauses.append("c.name = $context_filter")
            params["context_filter"] = context_filter

        if type_filter:
            where_clauses.append("m.memory_type = $type_filter")
            params["type_filter"] = type_filter.value

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # Get total count
        count_query = f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            WHERE {where_clause}
            RETURN count(DISTINCT m.id) as total
        """
        count_result = self._db.execute(count_query, parameters=params)
        total_count = count_result.get_next()[0] if count_result.has_next() else 0

        # Get memories
        query = f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            WHERE {where_clause}
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at, c.name as context,
                   collect(t.name) as tags
            ORDER BY m.created_at DESC
            SKIP $offset LIMIT $limit
        """
        params["offset"] = offset
        params["limit"] = limit

        result = self._db.execute(query, parameters=params)
        memories: list[MemoryWithContext] = []

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[7] if t]

            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            memories.append(self._row_to_memory(row))

        has_more = offset + len(memories) < total_count
        return memories, total_count, has_more

    def get_links(self, memory_id: str) -> list[MemoryLink]:
        """Get all outgoing links from a memory."""
        result = self._db.execute(
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
        result = self._db.execute(
            """
            MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(linked:Memory)
            OPTIONAL MATCH (linked)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (linked)-[:TAGGED_WITH]->(t:Tag)
            RETURN linked.id, linked.content, linked.summary, linked.memory_type,
                   linked.created_at, linked.updated_at, c.name,
                   collect(t.name) as tags, r.relation_type, r.reason
            LIMIT $limit
            """,
            parameters={"id": memory_id, "limit": max_per_category},
        )

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[7] if t]
            memory = MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                context=row[6],
                tags=tags,
                related_memories=[
                    MemoryLink(
                        target_id=memory_id,
                        relation_type=RelationType(row[8]),
                        reason=row[9] if row[9] else None,
                    )
                ],
            )
            result_dict["linked"].append(memory)

        # Get tag siblings
        if include_tag_siblings:
            result = self._db.execute(
                """
                MATCH (m:Memory {id: $id})-[:TAGGED_WITH]->(t:Tag)<-[:TAGGED_WITH]-(sibling:Memory)
                WHERE m <> sibling
                OPTIONAL MATCH (sibling)-[:ORIGINATED_IN]->(c:Context)
                OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(st:Tag)
                WITH sibling, c, collect(DISTINCT t.name) as shared_tags,
                     collect(DISTINCT st.name) as all_tags
                RETURN sibling.id, sibling.content, sibling.summary, sibling.memory_type,
                       sibling.created_at, sibling.updated_at, c.name, all_tags, shared_tags
                ORDER BY size(shared_tags) DESC
                LIMIT $limit
                """,
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
            result = self._db.execute(
                """
                MATCH (m:Memory {id: $id})-[:ORIGINATED_IN]->(c:Context)<-[:ORIGINATED_IN]-(sibling:Memory)
                WHERE m <> sibling
                OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(t:Tag)
                RETURN sibling.id, sibling.content, sibling.summary, sibling.memory_type,
                       sibling.created_at, sibling.updated_at, c.name,
                       collect(t.name) as tags
                ORDER BY sibling.created_at DESC
                LIMIT $limit
                """,
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
        # Get existing memory info
        result = self._db.execute(
            """
            MATCH (m:Memory {id: $id})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at, c.name as context
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

        changes: list[str] = []
        now = datetime.now(timezone.utc)
        summary = current_summary

        # If content changes, we need to delete and recreate due to vector index
        if content is not None:
            embedding = self._embedding_engine.embed(content)
            summary = self._generate_summary(content)
            new_type = memory_type.value if memory_type else current_type

            # Get existing RELATED_TO links (both directions)
            outgoing_links = []
            result = self._db.execute(
                """
                MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(t:Memory)
                RETURN t.id, r.relation_type, r.reason, r.created_at
                """,
                parameters={"id": memory_id},
            )
            while result.has_next():
                link_row = result.get_next()
                outgoing_links.append(link_row)

            incoming_links = []
            result = self._db.execute(
                """
                MATCH (s:Memory)-[r:RELATED_TO]->(m:Memory {id: $id})
                RETURN s.id, r.relation_type, r.reason, r.created_at
                """,
                parameters={"id": memory_id},
            )
            while result.has_next():
                link_row = result.get_next()
                incoming_links.append(link_row)

            # Delete the old memory node and its relationships
            self._db.execute(
                "MATCH (m:Memory {id: $id})-[r:ORIGINATED_IN]->(:Context) DELETE r",
                parameters={"id": memory_id},
            )
            self._db.execute(
                "MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag) DELETE r",
                parameters={"id": memory_id},
            )
            self._db.execute(
                "MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(:Memory) DELETE r",
                parameters={"id": memory_id},
            )
            self._db.execute(
                "MATCH (:Memory)-[r:RELATED_TO]->(m:Memory {id: $id}) DELETE r",
                parameters={"id": memory_id},
            )
            self._db.execute(
                "MATCH (m:Memory {id: $id}) DELETE m",
                parameters={"id": memory_id},
            )

            # Recreate memory with new content
            self._db.execute(
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
                self._db.execute(
                    """
                    MATCH (m:Memory {id: $memory_id}), (c:Context {name: $context_name})
                    CREATE (m)-[:ORIGINATED_IN]->(c)
                    """,
                    parameters={"memory_id": memory_id, "context_name": context_name},
                )

            # Re-create RELATED_TO links
            for link in outgoing_links:
                self._db.execute(
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
                self._db.execute(
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

        elif memory_type is not None:
            # Only updating type, no embedding change needed
            self._db.execute(
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

        if tags is not None:
            self._db.execute(
                """
                MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag)
                DELETE r
                """,
                parameters={"id": memory_id},
            )

            for tag in tags:
                tag_normalized = tag.strip().lower()
                if not tag_normalized:
                    continue

                self._db.execute(
                    """
                    MERGE (t:Tag {name: $name})
                    ON CREATE SET t.created_at = $created_at
                    """,
                    parameters={"name": tag_normalized, "created_at": now},
                )

                self._db.execute(
                    """
                    MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                    CREATE (m)-[:TAGGED_WITH]->(t)
                    """,
                    parameters={"memory_id": memory_id, "tag_name": tag_normalized},
                )

            changes.append("tags")

        if changes and content is None and memory_type is None:
            self._db.execute(
                """
                MATCH (m:Memory {id: $id})
                SET m.updated_at = $updated_at
                """,
                parameters={"id": memory_id, "updated_at": now},
            )

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
        result = self._db.execute(
            "MATCH (m:Memory {id: $id}) RETURN m.id",
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return False

        # Delete relationships
        self._db.execute(
            "MATCH (m:Memory {id: $id})-[r:ORIGINATED_IN]->(:Context) DELETE r",
            parameters={"id": memory_id},
        )
        self._db.execute(
            "MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag) DELETE r",
            parameters={"id": memory_id},
        )
        self._db.execute(
            "MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(:Memory) DELETE r",
            parameters={"id": memory_id},
        )
        self._db.execute(
            "MATCH (:Memory)-[r:RELATED_TO]->(m:Memory {id: $id}) DELETE r",
            parameters={"id": memory_id},
        )

        # Delete node
        self._db.execute(
            "MATCH (m:Memory {id: $id}) DELETE m",
            parameters={"id": memory_id},
        )

        logger.info(f"Deleted memory {memory_id}")
        return True

    def delete_link(self, source_id: str, target_id: str) -> bool:
        """Delete a link between two memories."""
        result = self._db.execute(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            return False

        self._db.execute(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            DELETE r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        logger.info(f"Unlinked memory {source_id} -> {target_id}")
        return True

    # =========================================================================
    # Statistics and Analysis
    # =========================================================================

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories."""
        result = self._db.execute("MATCH (m:Memory) RETURN count(m)")
        total_memories = result.get_next()[0] if result.has_next() else 0

        result = self._db.execute("""
            MATCH (m:Memory)
            RETURN m.memory_type, count(m) as count
        """)
        memories_by_type: dict[str, int] = {}
        while result.has_next():
            row = result.get_next()
            memories_by_type[row[0]] = row[1]

        result = self._db.execute("MATCH (c:Context) RETURN count(c)")
        total_contexts = result.get_next()[0] if result.has_next() else 0

        result = self._db.execute("MATCH (t:Tag) RETURN count(t)")
        total_tags = result.get_next()[0] if result.has_next() else 0

        result = self._db.execute("""
            MATCH (m:Memory)-[:TAGGED_WITH]->(t:Tag)
            RETURN t.name, count(m) as count
            ORDER BY count DESC
            LIMIT 10
        """)
        top_tags: list[dict[str, Any]] = []
        while result.has_next():
            row = result.get_next()
            top_tags.append({"name": row[0], "count": row[1]})

        return MemoryStats(
            total_memories=total_memories,
            memories_by_type=memories_by_type,
            total_contexts=total_contexts,
            total_tags=total_tags,
            top_tags=top_tags,
        )

    def analyze_health(self, stale_days: int = 90) -> AnalyzeKnowledgeResult:
        """Analyze knowledge base health."""
        issues: list[KnowledgeHealthIssue] = []
        suggestions: list[str] = []
        stats: dict[str, Any] = {}

        memory_stats = self.get_stats()
        total_memories = memory_stats.total_memories

        if total_memories == 0:
            return AnalyzeKnowledgeResult(
                total_memories=0,
                health_score=100.0,
                issues=[],
                suggestions=["Start storing memories to build your external brain!"],
                stats={},
            )

        # Check for orphan memories (no tags)
        result = self._db.execute("""
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:TAGGED_WITH]->(:Tag) }
            RETURN m.id, m.summary
        """)
        orphan_memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            orphan_memories.append((row[0], row[1]))

        if orphan_memories:
            issues.append(
                KnowledgeHealthIssue(
                    issue_type="orphan_memories",
                    severity="medium",
                    message=f"{len(orphan_memories)} memories have no tags.",
                    affected_memory_ids=[m[0] for m in orphan_memories[:10]],
                    suggested_action="Add tags using update_memory",
                )
            )

        # Check for unlinked memories
        result = self._db.execute("""
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:RELATED_TO]->(:Memory) }
              AND NOT EXISTS { MATCH (:Memory)-[:RELATED_TO]->(m) }
            RETURN count(m)
        """)
        unlinked_count = result.get_next()[0] if result.has_next() else 0
        stats["unlinked_memories"] = unlinked_count

        if unlinked_count > 0 and total_memories > 5:
            link_ratio = unlinked_count / total_memories
            if link_ratio > 0.8:
                issues.append(
                    KnowledgeHealthIssue(
                        issue_type="low_connectivity",
                        severity="low",
                        message=f"{unlinked_count}/{total_memories} memories have no links.",
                        affected_memory_ids=[],
                        suggested_action="Use explore_related and link_memories",
                    )
                )

        # Check for stale memories
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=stale_days)
        result = self._db.execute(
            """
            MATCH (m:Memory)
            WHERE m.updated_at < $threshold
            RETURN m.id, m.summary
            LIMIT 10
            """,
            parameters={"threshold": stale_threshold},
        )
        stale_memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            stale_memories.append((row[0], row[1]))

        if stale_memories:
            issues.append(
                KnowledgeHealthIssue(
                    issue_type="stale_memories",
                    severity="low",
                    message=f"{len(stale_memories)}+ memories not updated in {stale_days}+ days.",
                    affected_memory_ids=[m[0] for m in stale_memories],
                    suggested_action="Review and update or mark as superseded",
                )
            )

        # Calculate health score
        health_score = 100.0
        for issue in issues:
            if issue.severity == "high":
                health_score -= 20
            elif issue.severity == "medium":
                health_score -= 10
            elif issue.severity == "low":
                health_score -= 5

        if unlinked_count / total_memories < 0.5:
            health_score = min(100, health_score + 5)

        health_score = max(0, health_score)

        # Generate suggestions
        if not issues:
            suggestions.append("Your knowledge base looks healthy!")
        else:
            suggestions.append("Address the issues above to improve discoverability.")

        if total_memories < 10:
            suggestions.append("Keep recording insights for better semantic search.")

        if memory_stats.memories_by_type.get(MemoryType.FAILURE.value, 0) == 0:
            suggestions.append("Don't forget to record failures too!")

        return AnalyzeKnowledgeResult(
            total_memories=total_memories,
            health_score=health_score,
            issues=issues,
            suggestions=suggestions,
            stats=stats,
        )
