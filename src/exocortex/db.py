"""Database wrapper for Exocortex using KùzuDB."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import kuzu

from .config import get_config
from .embeddings import get_embedding_engine
from .models import (
    AnalyzeKnowledgeResult,
    KnowledgeHealthIssue,
    KnowledgeInsight,
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    RelationType,
    StoreMemoryResult,
    SuggestedLink,
)

logger = logging.getLogger(__name__)


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

        # Create RELATED_TO relationship table for memory-to-memory links
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS RELATED_TO (
                FROM Memory TO Memory,
                relation_type STRING,
                reason STRING,
                created_at TIMESTAMP
            )
        """)

        # Create vector index for efficient similarity search
        self._create_vector_index()

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
        config = get_config()
        max_length = config.max_summary_length

        # Simple truncation for now
        # Could be enhanced with AI summarization later
        content = content.strip()
        if len(content) <= max_length:
            return content

        # Truncate at word boundary
        truncated = content[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    def _row_to_memory_with_context(
        self,
        row: tuple,
        include_content: bool = True,
        similarity: float | None = None,
        related_memories: list[MemoryLink] | None = None,
    ) -> MemoryWithContext:
        """Convert a database row to MemoryWithContext.

        Standard row format: (id, content, summary, memory_type, created_at, updated_at, context, tags)

        Args:
            row: Database result row.
            include_content: Whether content is in the row (position 1).
            similarity: Optional similarity score.
            related_memories: Optional list of related memory links.

        Returns:
            MemoryWithContext object.
        """
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
                content="",  # Not included
                summary=row[1],
                memory_type=MemoryType(row[2]),
                created_at=row[3],
                updated_at=row[4],
                context=row[5],
                tags=tags,
                similarity=similarity,
                related_memories=related_memories or [],
            )

    def _validate_store_input(
        self, content: str, context_name: str, tags: list[str]
    ) -> None:
        """Validate input for store_memory.

        Args:
            content: Memory content.
            context_name: Context name.
            tags: List of tags.

        Raises:
            ValueError: If validation fails.
        """
        config = get_config()

        if not content or not content.strip():
            raise ValueError("Content cannot be empty")

        if not context_name or not context_name.strip():
            raise ValueError("Context name cannot be empty")

        if len(tags) > config.max_tags_per_memory:
            raise ValueError(
                f"Too many tags (max {config.max_tags_per_memory}, got {len(tags)})"
            )

    def store_memory(
        self,
        content: str,
        context_name: str,
        tags: list[str],
        memory_type: MemoryType = MemoryType.INSIGHT,
        auto_analyze: bool = True,
    ) -> StoreMemoryResult:
        """Store a new memory.

        Args:
            content: Memory content.
            context_name: Associated context/project.
            tags: Associated tags.
            memory_type: Type of memory.
            auto_analyze: Whether to analyze for similar memories and suggestions.

        Returns:
            StoreMemoryResult with success status, memory ID, and knowledge insights.

        Raises:
            ValueError: If input validation fails.
        """
        # Validate input
        self._validate_store_input(content, context_name, tags)

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

        # Auto-analyze for knowledge improvement suggestions
        suggested_links: list[SuggestedLink] = []
        insights: list[KnowledgeInsight] = []

        if auto_analyze:
            suggested_links, insights = self._analyze_new_memory(
                memory_id, content, embedding, memory_type, embedding_engine
            )

        return StoreMemoryResult(
            success=True,
            memory_id=memory_id,
            summary=summary,
            suggested_links=suggested_links,
            insights=insights,
        )

    def _analyze_new_memory(
        self,
        new_memory_id: str,
        content: str,
        embedding: list[float],
        memory_type: MemoryType,
        embedding_engine: Any,
    ) -> tuple[list[SuggestedLink], list[KnowledgeInsight]]:
        """Analyze a new memory for potential links and insights.

        Args:
            new_memory_id: ID of the newly created memory.
            content: Content of the new memory.
            embedding: Embedding vector of the new memory.
            memory_type: Type of the new memory.
            embedding_engine: Embedding engine for similarity computation.

        Returns:
            Tuple of (suggested_links, insights).
        """
        suggested_links: list[SuggestedLink] = []
        insights: list[KnowledgeInsight] = []

        # Get thresholds from config
        config = get_config()
        link_threshold = config.link_suggestion_threshold
        duplicate_threshold = config.duplicate_detection_threshold
        contradiction_threshold = config.contradiction_check_threshold

        contradiction_keywords = [
            "but", "however", "instead", "wrong", "incorrect",
            "not", "don't", "shouldn't", "actually", "contrary"
        ]

        # Get all other memories with embeddings
        result = self.conn.execute("""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            RETURN m.id, m.summary, m.embedding, m.memory_type, c.name as context
        """)

        similar_memories: list[tuple[str, str, float, str, str]] = []  # id, summary, similarity, type, context

        while result.has_next():
            row = result.get_next()
            other_id = row[0]
            other_summary = row[1]
            other_embedding = row[2]
            other_type = row[3]
            other_context = row[4]

            if other_id == new_memory_id:
                continue

            similarity = embedding_engine.compute_similarity(embedding, other_embedding)
            if similarity > link_threshold:
                similar_memories.append((other_id, other_summary, similarity, other_type, other_context))

        # Sort by similarity
        similar_memories.sort(key=lambda x: x[2], reverse=True)

        # Analyze similar memories
        for other_id, other_summary, similarity, other_type, other_context in similar_memories[:5]:
            # Check for potential duplicate
            if similarity > duplicate_threshold:
                insights.append(
                    KnowledgeInsight(
                        insight_type="potential_duplicate",
                        message=f"This memory is very similar ({similarity:.0%}) to an existing one. Consider updating instead of creating new.",
                        related_memory_id=other_id,
                        related_memory_summary=other_summary,
                        confidence=similarity,
                        suggested_action=f"Use update_memory on '{other_id}' or link with 'supersedes' relation",
                    )
                )
            else:
                # Suggest link based on relationship patterns
                suggested_relation = self._infer_relation_type(
                    memory_type, other_type, content, other_summary
                )
                reason = self._generate_link_reason(
                    memory_type, other_type, similarity, other_context
                )

                suggested_links.append(
                    SuggestedLink(
                        target_id=other_id,
                        target_summary=other_summary or "",
                        similarity=similarity,
                        suggested_relation=suggested_relation,
                        reason=reason,
                    )
                )

        # Check for potential contradictions (heuristic)
        content_lower = content.lower()
        has_contradiction_signals = any(kw in content_lower for kw in contradiction_keywords)

        if has_contradiction_signals and similar_memories:
            top_similar = similar_memories[0]
            if top_similar[2] > contradiction_threshold:
                insights.append(
                    KnowledgeInsight(
                        insight_type="potential_contradiction",
                        message="This memory may contradict or update existing knowledge. Please verify.",
                        related_memory_id=top_similar[0],
                        related_memory_summary=top_similar[1],
                        confidence=0.6,  # Heuristic-based, lower confidence
                        suggested_action="Review and consider linking with 'supersedes' or 'contradicts' relation",
                    )
                )

        # Insight: Suggest pattern-based improvements
        if memory_type == MemoryType.SUCCESS:
            # Check if there's a related failure that this might resolve
            for other_id, other_summary, similarity, other_type, _ in similar_memories:
                if other_type == MemoryType.FAILURE.value and similarity > 0.6:
                    insights.append(
                        KnowledgeInsight(
                            insight_type="success_after_failure",
                            message="This success may be a solution to a previously recorded failure.",
                            related_memory_id=other_id,
                            related_memory_summary=other_summary,
                            confidence=similarity,
                            suggested_action=f"Link to failure '{other_id}' with 'extends' relation to document the solution",
                        )
                    )
                    break

        return suggested_links, insights

    def _infer_relation_type(
        self,
        new_type: MemoryType,
        existing_type: str,
        new_content: str,
        existing_summary: str,
    ) -> RelationType:
        """Infer the most likely relation type between two memories.

        Args:
            new_type: Type of the new memory.
            existing_type: Type of the existing memory.
            new_content: Content of the new memory.
            existing_summary: Summary of the existing memory.

        Returns:
            Suggested RelationType.
        """
        new_content_lower = new_content.lower()

        # Pattern: Success extending/resolving insight or failure
        if new_type == MemoryType.SUCCESS:
            if existing_type in [MemoryType.INSIGHT.value, MemoryType.DECISION.value]:
                return RelationType.EXTENDS
            if existing_type == MemoryType.FAILURE.value:
                return RelationType.EXTENDS  # Solution to a problem

        # Pattern: Decision based on insight
        if new_type == MemoryType.DECISION:
            if existing_type == MemoryType.INSIGHT.value:
                return RelationType.DEPENDS_ON

        # Pattern: Content suggests superseding
        supersede_keywords = ["updated", "new version", "replaces", "improved", "better approach"]
        if any(kw in new_content_lower for kw in supersede_keywords):
            return RelationType.SUPERSEDES

        # Pattern: Content suggests contradiction
        contradict_keywords = ["wrong", "incorrect", "actually", "contrary", "opposite"]
        if any(kw in new_content_lower for kw in contradict_keywords):
            return RelationType.CONTRADICTS

        # Default to general relation
        return RelationType.RELATED

    def _generate_link_reason(
        self,
        new_type: MemoryType,
        existing_type: str,
        similarity: float,
        existing_context: str | None,
    ) -> str:
        """Generate a human-readable reason for a suggested link.

        Args:
            new_type: Type of the new memory.
            existing_type: Type of the existing memory.
            similarity: Similarity score.
            existing_context: Context of the existing memory.

        Returns:
            Reason string.
        """
        reasons = []

        if similarity > 0.85:
            reasons.append("Very high semantic similarity")
        elif similarity > 0.75:
            reasons.append("High semantic similarity")
        else:
            reasons.append("Moderate semantic similarity")

        if new_type == MemoryType.SUCCESS and existing_type == MemoryType.FAILURE.value:
            reasons.append("may be a solution to the recorded failure")
        elif new_type == MemoryType.SUCCESS and existing_type == MemoryType.INSIGHT.value:
            reasons.append("may be an application of this insight")
        elif new_type == MemoryType.DECISION and existing_type == MemoryType.INSIGHT.value:
            reasons.append("decision may be based on this insight")

        if existing_context:
            reasons.append(f"from project '{existing_context}'")

        return "; ".join(reasons)

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

        # Delete RELATED_TO relationships (both directions)
        self.conn.execute(
            """
            MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(:Memory)
            DELETE r
            """,
            parameters={"id": memory_id},
        )
        self.conn.execute(
            """
            MATCH (:Memory)-[r:RELATED_TO]->(m:Memory {id: $id})
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

    def link_memories(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        reason: str | None = None,
    ) -> tuple[bool, str]:
        """Create a link between two memories.

        Args:
            source_id: Source memory ID.
            target_id: Target memory ID.
            relation_type: Type of relationship.
            reason: Optional reason for the link.

        Returns:
            Tuple of (success, message). Message contains error description if failed.
        """
        # Check if source and target are the same
        if source_id == target_id:
            return False, "Cannot link a memory to itself"

        # Check both memories exist
        result = self.conn.execute(
            """
            MATCH (s:Memory {id: $source_id}), (t:Memory {id: $target_id})
            RETURN s.id, t.id
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            return False, "One or both memories not found"

        # Check if link already exists
        result = self.conn.execute(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r.relation_type
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if result.has_next():
            existing_type = result.get_next()[0]
            return False, f"Link already exists with relation type '{existing_type}'"

        now = datetime.now(timezone.utc)

        # Create the relationship
        self.conn.execute(
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
        return True, "Link created successfully"

    def unlink_memories(self, source_id: str, target_id: str) -> bool:
        """Remove a link between two memories.

        Args:
            source_id: Source memory ID.
            target_id: Target memory ID.

        Returns:
            True if link removed, False if not found.
        """
        # Check if link exists
        result = self.conn.execute(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            RETURN r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        if not result.has_next():
            return False

        # Delete the relationship
        self.conn.execute(
            """
            MATCH (s:Memory {id: $source_id})-[r:RELATED_TO]->(t:Memory {id: $target_id})
            DELETE r
            """,
            parameters={"source_id": source_id, "target_id": target_id},
        )

        logger.info(f"Unlinked memory {source_id} -> {target_id}")
        return True

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        memory_type: MemoryType | None = None,
    ) -> tuple[bool, list[str]]:
        """Update an existing memory.

        Args:
            memory_id: Memory ID to update.
            content: New content (updates embedding and summary too).
            tags: New tags (replaces existing tags).
            memory_type: New memory type.

        Returns:
            Tuple of (success, list of changes made).
        """
        # Check memory exists
        result = self.conn.execute(
            "MATCH (m:Memory {id: $id}) RETURN m.id",
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return False, []

        changes: list[str] = []
        now = datetime.now(timezone.utc)

        # Update content (and re-embed)
        if content is not None:
            embedding_engine = get_embedding_engine()
            embedding = embedding_engine.embed(content)
            summary = self._generate_summary(content)

            self.conn.execute(
                """
                MATCH (m:Memory {id: $id})
                SET m.content = $content,
                    m.summary = $summary,
                    m.embedding = $embedding,
                    m.updated_at = $updated_at
                """,
                parameters={
                    "id": memory_id,
                    "content": content,
                    "summary": summary,
                    "embedding": embedding,
                    "updated_at": now,
                },
            )
            changes.append("content")

        # Update memory type
        if memory_type is not None:
            self.conn.execute(
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

        # Update tags (replace all)
        if tags is not None:
            # Delete existing tag relationships
            self.conn.execute(
                """
                MATCH (m:Memory {id: $id})-[r:TAGGED_WITH]->(:Tag)
                DELETE r
                """,
                parameters={"id": memory_id},
            )

            # Create new tag relationships
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

            changes.append("tags")

        # Update timestamp if anything changed
        if changes and content is None and memory_type is None:
            self.conn.execute(
                """
                MATCH (m:Memory {id: $id})
                SET m.updated_at = $updated_at
                """,
                parameters={"id": memory_id, "updated_at": now},
            )

        logger.info(f"Updated memory {memory_id}: {changes}")
        return True, changes

    def get_memory_links(self, memory_id: str) -> list[MemoryLink]:
        """Get all links from a memory.

        Args:
            memory_id: Memory ID.

        Returns:
            List of MemoryLink objects.
        """
        result = self.conn.execute(
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
        """Explore memories related to a given memory through graph traversal.

        Args:
            memory_id: Center memory ID.
            include_tag_siblings: Include memories with same tags.
            include_context_siblings: Include memories in same context.
            max_per_category: Maximum results per category.

        Returns:
            Dictionary with 'linked', 'by_tag', 'by_context' keys.
        """
        result_dict: dict[str, list[MemoryWithContext]] = {
            "linked": [],
            "by_tag": [],
            "by_context": [],
        }

        # Get directly linked memories
        result = self.conn.execute(
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

        # Get memories with same tags (tag siblings)
        if include_tag_siblings:
            result = self.conn.execute(
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
                )
                result_dict["by_tag"].append(memory)
                seen_ids.add(row[0])

        # Get memories in same context
        if include_context_siblings:
            result = self.conn.execute(
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
                )
                result_dict["by_context"].append(memory)

        return result_dict

    def analyze_knowledge(self) -> AnalyzeKnowledgeResult:
        """Analyze the knowledge base for health issues and improvement opportunities.

        Returns:
            AnalyzeKnowledgeResult with health score, issues, and suggestions.
        """
        issues: list[KnowledgeHealthIssue] = []
        suggestions: list[str] = []
        stats: dict[str, Any] = {}

        # Get basic stats
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

        # Issue 1: Orphan memories (no tags)
        result = self.conn.execute("""
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
                    message=f"{len(orphan_memories)} memories have no tags, making them harder to discover.",
                    affected_memory_ids=[m[0] for m in orphan_memories[:10]],
                    suggested_action="Add tags to these memories using update_memory",
                )
            )

        # Issue 2: Unlinked memories (no RELATED_TO connections)
        result = self.conn.execute("""
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
                        message=f"{unlinked_count}/{total_memories} memories have no explicit links. "
                                "Consider linking related memories to build a knowledge graph.",
                        affected_memory_ids=[],
                        suggested_action="Use explore_related to find connections, then link_memories to connect them",
                    )
                )

        # Issue 3: Stale memories (not updated in long time)
        config = get_config()
        stale_threshold = datetime.now(timezone.utc) - timedelta(days=config.stale_memory_days)

        result = self.conn.execute(
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
                    message=f"{len(stale_memories)}+ memories haven't been updated in 90+ days. "
                            "They may need review.",
                    affected_memory_ids=[m[0] for m in stale_memories],
                    suggested_action="Review these memories and update or mark as superseded if outdated",
                )
            )

        # Issue 4: Tag normalization issues (similar tags)
        result = self.conn.execute("""
            MATCH (t:Tag)
            RETURN t.name
        """)
        all_tags: list[str] = []
        while result.has_next():
            all_tags.append(result.get_next()[0])

        # Simple heuristic: check for potential duplicates
        similar_tags: list[tuple[str, str]] = []
        for i, tag1 in enumerate(all_tags):
            for tag2 in all_tags[i + 1:]:
                # Check if one is substring of other or very similar
                if tag1 in tag2 or tag2 in tag1:
                    similar_tags.append((tag1, tag2))
                elif len(tag1) > 3 and len(tag2) > 3:
                    # Simple Levenshtein-like check
                    if abs(len(tag1) - len(tag2)) <= 2:
                        common = sum(1 for a, b in zip(tag1, tag2) if a == b)
                        if common / max(len(tag1), len(tag2)) > 0.8:
                            similar_tags.append((tag1, tag2))

        if similar_tags:
            issues.append(
                KnowledgeHealthIssue(
                    issue_type="similar_tags",
                    severity="low",
                    message=f"Found {len(similar_tags)} pairs of similar tags that might be duplicates: "
                            f"{similar_tags[:3]}",
                    affected_memory_ids=[],
                    suggested_action="Consider standardizing tags by updating memories with consistent tag names",
                )
            )

        # Issue 5: Context distribution imbalance
        result = self.conn.execute("""
            MATCH (m:Memory)-[:ORIGINATED_IN]->(c:Context)
            RETURN c.name, count(m) as count
            ORDER BY count DESC
        """)
        context_counts: list[tuple[str, int]] = []
        while result.has_next():
            row = result.get_next()
            context_counts.append((row[0], row[1]))

        stats["memories_per_context"] = dict(context_counts)

        # Calculate health score
        health_score = 100.0

        # Penalize for issues
        for issue in issues:
            if issue.severity == "high":
                health_score -= 20
            elif issue.severity == "medium":
                health_score -= 10
            elif issue.severity == "low":
                health_score -= 5

        # Bonus for good practices
        if unlinked_count / total_memories < 0.5:
            health_score = min(100, health_score + 5)

        health_score = max(0, health_score)

        # Generate suggestions
        if not issues:
            suggestions.append("Your knowledge base looks healthy! Keep building your external brain.")
        else:
            suggestions.append("Address the issues above to improve knowledge discoverability.")

        if total_memories < 10:
            suggestions.append("Keep recording insights - the more memories, the more useful semantic search becomes.")

        if memory_stats.memories_by_type.get(MemoryType.FAILURE.value, 0) == 0:
            suggestions.append("Don't forget to record failures too - they're valuable learning opportunities!")

        return AnalyzeKnowledgeResult(
            total_memories=total_memories,
            health_score=health_score,
            issues=issues,
            suggestions=suggestions,
            stats=stats,
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

