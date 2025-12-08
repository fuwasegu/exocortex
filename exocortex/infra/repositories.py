"""Repository pattern implementation for data access."""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..domain.exceptions import (
    DuplicateLinkError,
    MemoryNotFoundError,
    SelfLinkError,
)
from ..domain.models import (
    MemoryLink,
    MemoryStats,
    MemoryType,
    MemoryWithContext,
    Pattern,
    RelationType,
)
from .database import DatabaseConnection, SmartDatabaseManager
from .embeddings import EmbeddingEngine

if TYPE_CHECKING:
    import kuzu

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for memory data access operations.

    Supports smart connection management:
    - Read operations use read-only connections (allows concurrent access)
    - Write operations use read-write connections (exclusive lock with retry)
    """

    def __init__(
        self,
        db_manager: SmartDatabaseManager | DatabaseConnection,
        embedding_engine: EmbeddingEngine,
        max_summary_length: int = 200,
    ) -> None:
        """Initialize the repository.

        Args:
            db_manager: Smart database manager or legacy database connection.
            embedding_engine: Embedding engine for vector operations.
            max_summary_length: Maximum length for summaries.
        """
        self._db_manager = db_manager
        self._embedding_engine = embedding_engine
        self._max_summary_length = max_summary_length

        # Check if using smart manager or legacy connection
        self._use_smart_manager = isinstance(db_manager, SmartDatabaseManager)

    def _get_read_connection(self) -> DatabaseConnection:
        """Get a read-only database connection."""
        if self._use_smart_manager:
            return self._db_manager.read_connection  # type: ignore
        return self._db_manager  # type: ignore

    def _execute_read(
        self, query: str, parameters: dict | None = None
    ) -> kuzu.QueryResult:
        """Execute a read query using read-only connection."""
        conn = self._get_read_connection()
        if parameters:
            return conn.execute(query, parameters=parameters)
        return conn.execute(query)

    def _execute_write(
        self, query: str, parameters: dict | None = None
    ) -> kuzu.QueryResult:
        """Execute a write query using read-write connection.

        For smart manager, this uses the write context with retry logic.
        Note: Call _release_write_lock() after completing all writes in a batch.
        """
        if self._use_smart_manager:
            write_conn = self._db_manager.get_write_connection()  # type: ignore
            if parameters:
                return write_conn.execute(query, parameters=parameters)
            return write_conn.execute(query)
        else:
            # Legacy mode - use same connection
            if parameters:
                return self._db_manager.execute(query, parameters=parameters)  # type: ignore
            return self._db_manager.execute(query)  # type: ignore

    def _release_write_lock(self) -> None:
        """Release the write lock after completing write operations.

        This allows other processes to access the database immediately
        after write operations complete.
        """
        if self._use_smart_manager:
            self._db_manager.release_write_lock()  # type: ignore

    def compute_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Compute similarity between two embeddings.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Similarity score (0 to 1).
        """
        return self._embedding_engine.compute_similarity(embedding1, embedding2)

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

    def _create_tag_relationships(
        self, memory_id: str, tags: list[str], timestamp: datetime
    ) -> None:
        """Create tag nodes and relationships for a memory.

        Args:
            memory_id: The memory ID to tag.
            tags: List of tag names.
            timestamp: Timestamp for new tag nodes.
        """
        for tag in tags:
            tag_normalized = tag.strip().lower()
            if not tag_normalized:
                continue

            self._execute_write(
                """
                MERGE (t:Tag {name: $name})
                ON CREATE SET t.created_at = $created_at
                """,
                parameters={"name": tag_normalized, "created_at": timestamp},
            )

            self._execute_write(
                """
                MATCH (m:Memory {id: $memory_id}), (t:Tag {name: $tag_name})
                CREATE (m)-[:TAGGED_WITH]->(t)
                """,
                parameters={"memory_id": memory_id, "tag_name": tag_normalized},
            )

    def _row_to_memory(
        self,
        row: tuple,
        include_content: bool = True,
        similarity: float | None = None,
        related_memories: list[MemoryLink] | None = None,
    ) -> MemoryWithContext:
        """Convert a database row to MemoryWithContext.

        Row format with content (include_content=True):
            (id, content, summary, memory_type, created_at, updated_at,
             last_accessed_at, access_count, decay_rate,
             frustration_score, time_cost_hours, context, tags)

        Row format without content (include_content=False):
            (id, summary, memory_type, created_at, updated_at,
             last_accessed_at, access_count, decay_rate,
             frustration_score, time_cost_hours, context, tags)
        """
        if include_content:
            # Full row with dynamics and frustration fields
            tags = [t for t in row[12] if t] if row[12] else []
            return MemoryWithContext(
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
                similarity=similarity,
                related_memories=related_memories or [],
            )
        else:
            # Summary row with dynamics and frustration fields
            tags = [t for t in row[11] if t] if row[11] else []
            return MemoryWithContext(
                id=row[0],
                content="",
                summary=row[1],
                memory_type=MemoryType(row[2]),
                created_at=row[3],
                updated_at=row[4],
                last_accessed_at=row[5],
                access_count=row[6] if row[6] is not None else 1,
                decay_rate=row[7] if row[7] is not None else 0.1,
                frustration_score=row[8] if row[8] is not None else 0.0,
                time_cost_hours=row[9],
                context=row[10],
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
                "last_accessed_at": now,  # Initially set to creation time
                "access_count": 1,
                "decay_rate": 0.1,  # Default decay rate
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

        # Release write lock immediately after completing all writes
        self._release_write_lock()

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

        # Release write lock immediately
        self._release_write_lock()

        logger.info(f"Linked memory {source_id} -> {target_id} ({relation_type.value})")

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_by_id(self, memory_id: str) -> MemoryWithContext | None:
        """Get a memory by ID."""
        result = self._execute_read(
            """
            MATCH (m:Memory {id: $id})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at,
                   m.last_accessed_at, m.access_count, m.decay_rate,
                   m.frustration_score, m.time_cost_hours,
                   c.name as context, collect(t.name) as tags
            """,
            parameters={"id": memory_id},
        )

        if not result.has_next():
            return None

        return self._row_to_memory(result.get_next())

    def search_similar_by_embedding(
        self,
        embedding: list[float],
        limit: int = 10,
        exclude_id: str | None = None,
    ) -> list[tuple[str, str, float, str, str | None]]:
        """Search similar memories using KùzuDB native vector search.

        Uses the vector index for efficient similarity search.

        Args:
            embedding: Query embedding vector.
            limit: Maximum results to return.
            exclude_id: Optional memory ID to exclude from results.

        Returns:
            List of (id, summary, similarity, memory_type, context) tuples,
            sorted by similarity descending.
        """
        # Use KùzuDB's native vector search
        # Fetch more than needed to account for exclusions
        fetch_limit = limit + 5 if exclude_id else limit

        try:
            result = self._execute_read(
                """
                CALL QUERY_VECTOR_INDEX('Memory', 'memory_embedding_idx', $embedding, $k)
                YIELD node, distance
                MATCH (node)
                OPTIONAL MATCH (node)-[:ORIGINATED_IN]->(c:Context)
                RETURN node.id, node.summary, 1 - distance as similarity,
                       node.memory_type, c.name as context
                ORDER BY similarity DESC
                """,
                parameters={"embedding": embedding, "k": fetch_limit},
            )
        except Exception as e:
            # Fallback to brute-force if vector index fails
            logger.warning(f"Vector index search failed, using fallback: {e}")
            return self._search_similar_fallback(embedding, limit, exclude_id)

        memories = []
        while result.has_next():
            row = result.get_next()
            if exclude_id and row[0] == exclude_id:
                continue
            memories.append((row[0], row[1], row[2], row[3], row[4]))
            if len(memories) >= limit:
                break

        return memories

    def _search_similar_fallback(
        self,
        embedding: list[float],
        limit: int,
        exclude_id: str | None,
    ) -> list[tuple[str, str, float, str, str | None]]:
        """Fallback similarity search using Python-side computation.

        Used when vector index is not available.
        """
        result = self._execute_read("""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            RETURN m.id, m.summary, m.embedding, m.memory_type, c.name as context
        """)

        memories_with_scores: list[tuple[str, str, float, str, str | None]] = []

        while result.has_next():
            row = result.get_next()
            memory_id = row[0]
            if exclude_id and memory_id == exclude_id:
                continue

            similarity = self._embedding_engine.compute_similarity(embedding, row[2])
            memories_with_scores.append((memory_id, row[1], similarity, row[3], row[4]))

        memories_with_scores.sort(key=lambda x: x[2], reverse=True)
        return memories_with_scores[:limit]

    def search_by_similarity(
        self,
        query: str,
        limit: int = 5,
        context_filter: str | None = None,
        tag_filter: list[str] | None = None,
        type_filter: MemoryType | None = None,
        use_hybrid_scoring: bool = True,
    ) -> tuple[list[MemoryWithContext], int]:
        """Search memories by semantic similarity with hybrid scoring.

        Uses KùzuDB's native vector index for efficient search, then applies
        a hybrid scoring algorithm combining:
        - Vector similarity (semantic relevance)
        - Recency (time since last access)
        - Frequency (access count)

        Args:
            query: Search query.
            limit: Maximum results.
            context_filter: Filter by context.
            tag_filter: Filter by tags.
            type_filter: Filter by type.
            use_hybrid_scoring: If True, apply hybrid scoring algorithm.

        Returns:
            Tuple of (memories, total_found).
        """
        query_embedding = self._embedding_engine.embed(query)

        # Fetch more candidates to account for filtering and reranking
        fetch_multiplier = 5 if use_hybrid_scoring else 3
        if context_filter or tag_filter or type_filter:
            fetch_multiplier += 2
        candidates = self.search_similar_by_embedding(
            embedding=query_embedding,
            limit=limit * fetch_multiplier + 20,
        )

        memories: list[MemoryWithContext] = []

        for memory_id, _summary, similarity, memory_type, context in candidates:
            # Apply filters
            if context_filter and context != context_filter:
                continue
            if type_filter and memory_type != type_filter.value:
                continue

            # Get full memory with tags for tag filtering
            full_memory = self.get_by_id(memory_id)
            if full_memory is None:
                continue

            if tag_filter:
                tag_set = set(full_memory.tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            full_memory.similarity = similarity
            memories.append(full_memory)

        # Apply hybrid scoring if enabled
        if use_hybrid_scoring and memories:
            memories = self._apply_hybrid_scoring(memories)

        # Return top N after reranking
        return memories[:limit], len(memories[:limit])

    def _apply_hybrid_scoring(
        self,
        memories: list[MemoryWithContext],
        w_vec: float = 0.5,
        w_recency: float = 0.2,
        w_freq: float = 0.15,
        w_frustration: float = 0.15,
        decay_lambda: float = 0.01,
    ) -> list[MemoryWithContext]:
        """Apply hybrid scoring algorithm to rerank memories.

        Combines four signals (Somatic Marker Hypothesis integration):
        - S_vec: Vector similarity score (0-1)
        - S_recency: Recency score based on last_accessed_at (exponential decay)
        - S_freq: Frequency score based on access_count (logarithmic scale)
        - S_frustration: Frustration score - painful memories are prioritized

        Formula: Score = (S_vec * w_vec) + (S_recency * w_recency) +
                        (S_freq * w_freq) + (S_frustration * w_frustration)

        Args:
            memories: List of memories to rerank.
            w_vec: Weight for vector similarity (default: 0.5).
            w_recency: Weight for recency score (default: 0.2).
            w_freq: Weight for frequency score (default: 0.15).
            w_frustration: Weight for frustration score (default: 0.15).
            decay_lambda: Decay rate for recency calculation (default: 0.01 per day).

        Returns:
            Reranked list of memories with updated similarity scores.
        """
        now = datetime.now(timezone.utc)
        scored_memories: list[tuple[float, MemoryWithContext]] = []

        # Find max access_count for normalization
        max_access = max((m.access_count for m in memories), default=1)
        max_log_access = math.log(1 + max_access)

        for memory in memories:
            # S_vec: Vector similarity (already 0-1)
            s_vec = memory.similarity if memory.similarity is not None else 0.0

            # S_recency: Exponential decay based on time since last access
            # Uses last_accessed_at if available, otherwise created_at
            reference_time = memory.last_accessed_at or memory.created_at
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=timezone.utc)
            delta_days = (now - reference_time).total_seconds() / 86400.0
            s_recency = math.exp(-decay_lambda * delta_days)

            # S_freq: Logarithmic scale for access count (normalized)
            access_count = memory.access_count if memory.access_count else 1
            s_freq = (
                math.log(1 + access_count) / max_log_access if max_log_access > 0 else 0
            )

            # S_frustration: Frustration score (Somatic Marker Hypothesis)
            # Painful memories should be prioritized in decision-making
            s_frustration = memory.frustration_score if memory.frustration_score else 0.0

            # Combined hybrid score with frustration boost
            hybrid_score = (
                (s_vec * w_vec)
                + (s_recency * w_recency)
                + (s_freq * w_freq)
                + (s_frustration * w_frustration)
            )

            # Store original similarity for transparency, but sort by hybrid score
            scored_memories.append((hybrid_score, memory))

            logger.debug(
                f"Memory {memory.id[:8]}... hybrid={hybrid_score:.3f} "
                f"(vec={s_vec:.3f}, recency={s_recency:.3f}, "
                f"freq={s_freq:.3f}, frustration={s_frustration:.3f})"
            )

        # Sort by hybrid score (descending)
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Update similarity field with hybrid score for transparency
        result = []
        for hybrid_score, memory in scored_memories:
            memory.similarity = hybrid_score
            result.append(memory)

        return result

    def touch_memory(self, memory_id: str) -> bool:
        """Update memory access metadata (last_accessed_at, access_count).

        Should be called when a memory is returned in search results or accessed.

        Args:
            memory_id: The memory ID to touch.

        Returns:
            True if successful, False if memory not found.
        """
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
        """Batch update memory access metadata for multiple memories.

        Args:
            memory_ids: List of memory IDs to touch.

        Returns:
            Number of memories successfully touched.
        """
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
        count_result = self._execute_read(count_query, parameters=params)
        total_count = count_result.get_next()[0] if count_result.has_next() else 0

        # Get memories with dynamics and frustration fields
        query = f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            WHERE {where_clause}
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at,
                   m.last_accessed_at, m.access_count, m.decay_rate,
                   m.frustration_score, m.time_cost_hours,
                   c.name as context, collect(t.name) as tags
            ORDER BY m.created_at DESC
            SKIP $offset LIMIT $limit
        """
        params["offset"] = offset
        params["limit"] = limit

        result = self._execute_read(query, parameters=params)
        memories: list[MemoryWithContext] = []

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[12] if t]  # Updated index for tags

            if tag_filter:
                tag_set = set(tags)
                if not any(t.lower() in tag_set for t in tag_filter):
                    continue

            memories.append(self._row_to_memory(row))

        has_more = offset + len(memories) < total_count
        return memories, total_count, has_more

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
            """
            MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(linked:Memory)
            OPTIONAL MATCH (linked)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (linked)-[:TAGGED_WITH]->(t:Tag)
            RETURN linked.id, linked.content, linked.summary, linked.memory_type,
                   linked.created_at, linked.updated_at,
                   linked.last_accessed_at, linked.access_count, linked.decay_rate,
                   c.name, collect(t.name) as tags, r.relation_type, r.reason
            LIMIT $limit
            """,
            parameters={"id": memory_id, "limit": max_per_category},
        )

        while result.has_next():
            row = result.get_next()
            tags = [t for t in row[10] if t]
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
                context=row[9],
                tags=tags,
                related_memories=[
                    MemoryLink(
                        target_id=memory_id,
                        relation_type=RelationType(row[11]),
                        reason=row[12] if row[12] else None,
                    )
                ],
            )
            result_dict["linked"].append(memory)

        # Get tag siblings
        if include_tag_siblings:
            result = self._execute_read(
                """
                MATCH (m:Memory {id: $id})-[:TAGGED_WITH]->(t:Tag)<-[:TAGGED_WITH]-(sibling:Memory)
                WHERE m <> sibling
                OPTIONAL MATCH (sibling)-[:ORIGINATED_IN]->(c:Context)
                OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(st:Tag)
                WITH sibling, c, collect(DISTINCT t.name) as shared_tags,
                     collect(DISTINCT st.name) as all_tags
                RETURN sibling.id, sibling.content, sibling.summary, sibling.memory_type,
                       sibling.created_at, sibling.updated_at,
                       sibling.last_accessed_at, sibling.access_count, sibling.decay_rate,
                       c.name, all_tags, shared_tags
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
            result = self._execute_read(
                """
                MATCH (m:Memory {id: $id})-[:ORIGINATED_IN]->(c:Context)<-[:ORIGINATED_IN]-(sibling:Memory)
                WHERE m <> sibling
                OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(t:Tag)
                RETURN sibling.id, sibling.content, sibling.summary, sibling.memory_type,
                       sibling.created_at, sibling.updated_at,
                       sibling.last_accessed_at, sibling.access_count, sibling.decay_rate,
                       c.name, collect(t.name) as tags
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

        # Release write lock immediately
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

        # Release write lock immediately
        self._release_write_lock()

        logger.info(f"Deleted memory {memory_id}")
        return True

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

        # Release write lock immediately
        self._release_write_lock()

        logger.info(f"Unlinked memory {source_id} -> {target_id}")
        return True

    # =========================================================================
    # Statistics and Analysis (Data Queries)
    # =========================================================================

    def get_stats(self) -> MemoryStats:
        """Get statistics about stored memories."""
        result = self._execute_read("MATCH (m:Memory) RETURN count(m)")
        total_memories = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("""
            MATCH (m:Memory)
            RETURN m.memory_type, count(m) as count
        """)
        memories_by_type: dict[str, int] = {}
        while result.has_next():
            row = result.get_next()
            memories_by_type[row[0]] = row[1]

        result = self._execute_read("MATCH (c:Context) RETURN count(c)")
        total_contexts = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("MATCH (t:Tag) RETURN count(t)")
        total_tags = result.get_next()[0] if result.has_next() else 0

        result = self._execute_read("""
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

    def get_orphan_memories(self, limit: int = 10) -> list[tuple[str, str]]:
        """Get memories without tags.

        Args:
            limit: Maximum number of memories to return.

        Returns:
            List of (id, summary) tuples for memories without tags.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:TAGGED_WITH]->(:Tag) }
            RETURN m.id, m.summary
            LIMIT $limit
            """,
            parameters={"limit": limit},
        )
        memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            memories.append((row[0], row[1]))
        return memories

    def get_unlinked_count(self) -> int:
        """Get count of memories without any RELATED_TO links."""
        result = self._execute_read("""
            MATCH (m:Memory)
            WHERE NOT EXISTS { MATCH (m)-[:RELATED_TO]->(:Memory) }
              AND NOT EXISTS { MATCH (:Memory)-[:RELATED_TO]->(m) }
            RETURN count(m)
        """)
        return result.get_next()[0] if result.has_next() else 0

    def get_stale_memories(
        self, threshold: datetime, limit: int = 10
    ) -> list[tuple[str, str]]:
        """Get memories not updated since threshold.

        Args:
            threshold: Datetime threshold. Memories not updated since this time are stale.
            limit: Maximum number of memories to return.

        Returns:
            List of (id, summary) tuples for stale memories.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE m.updated_at < $threshold
            RETURN m.id, m.summary
            LIMIT $limit
            """,
            parameters={"threshold": threshold, "limit": limit},
        )
        memories: list[tuple[str, str]] = []
        while result.has_next():
            row = result.get_next()
            memories.append((row[0], row[1]))
        return memories

    # =========================================================================
    # Pattern Methods (Phase 2: Concept Abstraction)
    # =========================================================================

    def create_pattern(
        self,
        content: str,
        confidence: float = 0.5,
    ) -> tuple[str, str, list[float]]:
        """Create a new pattern in the database.

        Args:
            content: Pattern content (the generalized rule/insight).
            confidence: Initial confidence score (0.0-1.0).

        Returns:
            Tuple of (pattern_id, summary, embedding).
        """
        pattern_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        summary = self._generate_summary(content)
        embedding = self._embedding_engine.embed(content)

        self._execute_write(
            """
            CREATE (p:Pattern {
                id: $id,
                content: $content,
                summary: $summary,
                embedding: $embedding,
                confidence: $confidence,
                instance_count: $instance_count,
                created_at: $created_at,
                updated_at: $updated_at
            })
            """,
            parameters={
                "id": pattern_id,
                "content": content,
                "summary": summary,
                "embedding": embedding,
                "confidence": confidence,
                "instance_count": 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        self._release_write_lock()

        logger.info(f"Created pattern {pattern_id}")
        return pattern_id, summary, embedding

    def link_memory_to_pattern(
        self,
        memory_id: str,
        pattern_id: str,
        confidence: float = 0.5,
    ) -> bool:
        """Link a memory as an instance of a pattern.

        Args:
            memory_id: The memory ID.
            pattern_id: The pattern ID.
            confidence: How strongly this memory exemplifies the pattern.

        Returns:
            True if successful.
        """
        now = datetime.now(timezone.utc)

        # Check if link already exists
        result = self._execute_read(
            """
            MATCH (m:Memory {id: $memory_id})-[r:INSTANCE_OF]->(p:Pattern {id: $pattern_id})
            RETURN count(r) as cnt
            """,
            parameters={"memory_id": memory_id, "pattern_id": pattern_id},
        )
        if result.has_next() and result.get_next()[0] > 0:
            logger.debug(f"Link already exists: {memory_id} -> {pattern_id}")
            return True

        # Create the link
        self._execute_write(
            """
            MATCH (m:Memory {id: $memory_id}), (p:Pattern {id: $pattern_id})
            CREATE (m)-[:INSTANCE_OF {confidence: $confidence, created_at: $created_at}]->(p)
            """,
            parameters={
                "memory_id": memory_id,
                "pattern_id": pattern_id,
                "confidence": confidence,
                "created_at": now,
            },
        )

        # Update pattern's instance count and confidence
        self._execute_write(
            """
            MATCH (p:Pattern {id: $pattern_id})
            SET p.instance_count = p.instance_count + 1,
                p.updated_at = $now,
                p.confidence = CASE
                    WHEN p.confidence < 0.9 THEN p.confidence + 0.05
                    ELSE p.confidence
                END
            """,
            parameters={"pattern_id": pattern_id, "now": now},
        )
        self._release_write_lock()

        logger.info(f"Linked memory {memory_id} to pattern {pattern_id}")
        return True

    def search_similar_patterns(
        self,
        embedding: list[float],
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[tuple[str, str, float, float]]:
        """Search for similar patterns by embedding.

        Args:
            embedding: Query embedding vector.
            limit: Maximum results to return.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of (id, summary, similarity, confidence) tuples.
        """
        # KùzuDB vector search for patterns
        try:
            # First, try to use vector index if it exists for Pattern table
            result = self._execute_read(
                """
                MATCH (p:Pattern)
                WHERE p.confidence >= $min_confidence
                RETURN p.id, p.summary, p.embedding, p.confidence
                """,
                parameters={"min_confidence": min_confidence},
            )

            # Compute similarity manually (Pattern table may not have vector index)
            patterns = []
            while result.has_next():
                row = result.get_next()
                if row[2]:  # has embedding
                    similarity = self.compute_similarity(embedding, row[2])
                    patterns.append((row[0], row[1], similarity, row[3]))

            # Sort by similarity and return top N
            patterns.sort(key=lambda x: x[2], reverse=True)
            return patterns[:limit]

        except Exception as e:
            logger.warning(f"Pattern search error: {e}")
            return []

    def get_pattern_by_id(self, pattern_id: str) -> Pattern | None:
        """Get a pattern by ID.

        Args:
            pattern_id: The pattern ID.

        Returns:
            Pattern model or None if not found.
        """
        from ..domain.models import Pattern

        result = self._execute_read(
            """
            MATCH (p:Pattern {id: $id})
            RETURN p.id, p.content, p.summary, p.confidence,
                   p.instance_count, p.created_at, p.updated_at
            """,
            parameters={"id": pattern_id},
        )

        if not result.has_next():
            return None

        row = result.get_next()
        return Pattern(
            id=row[0],
            content=row[1],
            summary=row[2],
            confidence=row[3] if row[3] is not None else 0.5,
            instance_count=row[4] if row[4] is not None else 0,
            created_at=row[5],
            updated_at=row[6],
        )

    def get_memories_by_tag(
        self,
        tag: str,
        limit: int = 50,
    ) -> list[MemoryWithContext]:
        """Get memories with a specific tag.

        Args:
            tag: Tag name to filter by.
            limit: Maximum results.

        Returns:
            List of memories with the tag.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)-[:TAGGED_WITH]->(t:Tag {name: $tag})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(all_tags:Tag)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at,
                   m.last_accessed_at, m.access_count, m.decay_rate,
                   c.name, collect(DISTINCT all_tags.name) as tags
            ORDER BY m.access_count DESC
            LIMIT $limit
            """,
            parameters={"tag": tag.lower(), "limit": limit},
        )

        memories = []
        while result.has_next():
            row = result.get_next()
            memories.append(self._row_to_memory(row))

        return memories

    def get_frequently_accessed_memories(
        self,
        min_access_count: int = 3,
        limit: int = 100,
    ) -> list[MemoryWithContext]:
        """Get memories that are frequently accessed.

        Args:
            min_access_count: Minimum access count threshold.
            limit: Maximum results.

        Returns:
            List of frequently accessed memories.
        """
        result = self._execute_read(
            """
            MATCH (m:Memory)
            WHERE m.access_count >= $min_count
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN m.id, m.content, m.summary, m.memory_type,
                   m.created_at, m.updated_at,
                   m.last_accessed_at, m.access_count, m.decay_rate,
                   c.name, collect(t.name) as tags
            ORDER BY m.access_count DESC
            LIMIT $limit
            """,
            parameters={"min_count": min_access_count, "limit": limit},
        )

        memories = []
        while result.has_next():
            row = result.get_next()
            memories.append(self._row_to_memory(row))

        return memories
