"""Database wrapper for Exocortex using KùzuDB."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu

from .config import get_config
from .embeddings import get_embedding_engine
from .models import (
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    StoreMemoryResult,
)

logger = logging.getLogger(__name__)

# Maximum summary length (characters)
MAX_SUMMARY_LENGTH = 200


class ExocortexDB:
    """Database wrapper for Exocortex."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the database.

        Args:
            db_path: Path to the database directory. If None, uses config default.
        """
        self._db_path = db_path or get_config().data_dir / "exocortex_db"
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._initialized = False

    @property
    def db(self) -> kuzu.Database:
        """Get the database instance."""
        if self._db is None:
            logger.info(f"Initializing database at: {self._db_path}")
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = kuzu.Database(str(self._db_path))
        return self._db

    @property
    def conn(self) -> kuzu.Connection:
        """Get a database connection."""
        if self._conn is None:
            self._conn = kuzu.Connection(self.db)
            if not self._initialized:
                self._init_schema()
                self._initialized = True
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        logger.info("Initializing database schema...")

        # Get embedding dimension
        embedding_engine = get_embedding_engine()
        dim = embedding_engine.dimension

        # Create Memory node table
        self.conn.execute(f"""
            CREATE NODE TABLE IF NOT EXISTS Memory (
                id STRING,
                content STRING,
                summary STRING,
                embedding FLOAT[{dim}],
                memory_type STRING,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)

        # Create Context node table
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Context (
                name STRING,
                created_at TIMESTAMP,
                PRIMARY KEY (name)
            )
        """)

        # Create Tag node table
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Tag (
                name STRING,
                created_at TIMESTAMP,
                PRIMARY KEY (name)
            )
        """)

        # Create relationship tables
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS ORIGINATED_IN (
                FROM Memory TO Context
            )
        """)

        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS TAGGED_WITH (
                FROM Memory TO Tag
            )
        """)

        logger.info("Database schema initialized successfully")

    def _create_vector_index(self) -> None:
        """Create vector index for memory embeddings."""
        try:
            self.conn.execute("""
                CALL CREATE_VECTOR_INDEX(
                    'Memory',
                    'memory_embedding_idx',
                    'embedding',
                    metric := 'cosine'
                )
            """)
            logger.info("Vector index created successfully")
        except Exception as e:
            # Index might already exist
            logger.debug(f"Vector index creation skipped: {e}")

    def _generate_summary(self, content: str) -> str:
        """Generate a summary from content.

        Args:
            content: Full content text.

        Returns:
            Truncated summary.
        """
        # Simple truncation for now
        # Could be enhanced with AI summarization later
        content = content.strip()
        if len(content) <= MAX_SUMMARY_LENGTH:
            return content

        # Truncate at word boundary
        truncated = content[:MAX_SUMMARY_LENGTH]
        last_space = truncated.rfind(" ")
        if last_space > MAX_SUMMARY_LENGTH * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    def store_memory(
        self,
        content: str,
        context_name: str,
        tags: list[str],
        memory_type: MemoryType = MemoryType.INSIGHT,
    ) -> StoreMemoryResult:
        """Store a new memory.

        Args:
            content: Memory content.
            context_name: Associated context/project.
            tags: Associated tags.
            memory_type: Type of memory.

        Returns:
            StoreMemoryResult with success status and memory ID.
        """
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        summary = self._generate_summary(content)

        # Generate embedding
        embedding_engine = get_embedding_engine()
        embedding = embedding_engine.embed(content)

        # Store memory node
        self.conn.execute(
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
        self.conn.execute(
            """
            MERGE (c:Context {name: $name})
            ON CREATE SET c.created_at = $created_at
            """,
            parameters={"name": context_name, "created_at": now},
        )

        # Create relationship to context
        self.conn.execute(
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

            self.conn.execute(
                """
                MERGE (t:Tag {name: $name})
                ON CREATE SET t.created_at = $created_at
                """,
                parameters={"name": tag_normalized, "created_at": now},
            )

            self.conn.execute(
                """
                MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"memory_id": memory_id, "tag_name": tag_normalized},
            )

        logger.info(f"Stored memory {memory_id} with {len(tags)} tags")

        return StoreMemoryResult(
            success=True,
            memory_id=memory_id,
            summary=summary,
        )

    def recall_memories(
        self,
        query: str,
        limit: int = 5,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
    ) -> tuple[list[MemoryWithContext], int]:
        """Recall memories using semantic search.

        Args:
            query: Search query.
            limit: Maximum number of results.
            context_filter: Filter by context name.
            tag_filter: Filter by tags.
            type_filter: Filter by memory type.

        Returns:
            Tuple of (list of memories, total found count).
        """
        # Generate query embedding
        embedding_engine = get_embedding_engine()
        query_embedding = embedding_engine.embed(query)

        # Get all memories with embeddings for now
        # (KùzuDB vector search syntax may vary by version)
        result = self.conn.execute("""
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
            tags = [t for t in row[8] if t]  # Filter out None values

            # Apply filters
            if context_filter and context != context_filter:
                continue
            if type_filter and memory_type != type_filter.value:
                continue
            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            # Compute similarity
            similarity = embedding_engine.compute_similarity(query_embedding, embedding)

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

        # Sort by similarity and limit
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
        """List memories with pagination.

        Args:
            limit: Maximum number of results.
            offset: Offset for pagination.
            context_filter: Filter by context name.
            tag_filter: Filter by tags.
            type_filter: Filter by memory type.

        Returns:
            Tuple of (list of memories, total count, has_more).
        """
        # Build query with filters
        where_clauses = []
        params: dict[str, Any] = {}

        if context_filter:
            where_clauses.append("c.name = $context_filter")
            params["context_filter"] = context_filter

        if type_filter:
            where_clauses.append("m.memory_type = $type_filter")
            params["type_filter"] = type_filter.value

        where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # Get total count first
        count_query = f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            WHERE {where_clause}
            RETURN count(DISTINCT m.id) as total
        """
        count_result = self.conn.execute(count_query, parameters=params)
        total_count = count_result.get_next()[0] if count_result.has_next() else 0

        # Get memories with pagination
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

        result = self.conn.execute(query, parameters=params)
        memories: list[MemoryWithContext] = []

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[7] if t]

            # Apply tag filter in post-processing
            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            memory = MemoryWithContext(
                id=row[0],
                content=row[1],
                summary=row[2],
                memory_type=MemoryType(row[3]),
                created_at=row[4],
                updated_at=row[5],
                context=row[6],
                tags=tags,
            )
            memories.append(memory)

        has_more = offset + len(memories) < total_count

        return memories, total_count, has_more

    def get_memory(self, memory_id: str) -> MemoryWithContext | None:
        """Get a specific memory by ID.

        Args:
            memory_id: Memory ID.

        Returns:
            Memory if found, None otherwise.
        """
        result = self.conn.execute(
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

        row = result.get_next()
        tags = [t for t in row[7] if t]

        return MemoryWithContext(
            id=row[0],
            content=row[1],
            summary=row[2],
            memory_type=MemoryType(row[3]),
            created_at=row[4],
            updated_at=row[5],
            context=row[6],
            tags=tags,
        )

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: Memory ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        # Check if memory exists
        result = self.conn.execute(
            "MATCH (m:Memory {id: $id}) RETURN m.id",
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return False

        # Delete ORIGINATED_IN relationships
        self.conn.execute(
            """
            MATCH (m:Memory {id: $id})-[r:ORIGINATED_IN]->(:Context)
            DELETE r
            """,
            parameters={"id": memory_id},
        )

        # Delete TAGGED_WITH relationships
        self.conn.execute(
            """
            MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag)
            DELETE r
            """,
            parameters={"id": memory_id},
        )

        # Delete memory node
        self.conn.execute(
            """
            MATCH (m:Memory {id: $id})
            DELETE m
            """,
            parameters={"id": memory_id},
        )

        logger.info(f"Deleted memory {memory_id}")
        return True

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories.

        Returns:
            MemoryStats object.
        """
        # Total memories
        result = self.conn.execute("MATCH (m:Memory) RETURN count(m)")
        total_memories = result.get_next()[0] if result.has_next() else 0

        # Memories by type
        result = self.conn.execute("""
            MATCH (m:Memory)
            RETURN m.memory_type, count(m) as count
        """)
        memories_by_type: dict[str, int] = {}
        while result.has_next():
            row = result.get_next()
            memories_by_type[row[0]] = row[1]

        # Total contexts
        result = self.conn.execute("MATCH (c:Context) RETURN count(c)")
        total_contexts = result.get_next()[0] if result.has_next() else 0

        # Total tags
        result = self.conn.execute("MATCH (t:Tag) RETURN count(t)")
        total_tags = result.get_next()[0] if result.has_next() else 0

        # Top tags
        result = self.conn.execute("""
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

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn = None
        if self._db is not None:
            self._db = None
        logger.info("Database connection closed")


# Global database instance
_db: ExocortexDB | None = None


def get_db() -> ExocortexDB:
    """Get the global database instance."""
    global _db
    if _db is None:
        _db = ExocortexDB()
    return _db


def reset_db() -> None:
    """Reset the global database instance (useful for testing)."""
    global _db
    if _db is not None:
        _db.close()
    _db = None

