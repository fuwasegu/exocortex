"""Centralized query definitions for Memory operations.

This module defines all Cypher queries and column mappings for Memory-related
database operations. By centralizing these definitions, we prevent the
"column index mismatch" problem that caused 10 test failures when adding
frustration_score and time_cost_hours columns.

Usage:
    from exocortex.infra.queries import MemoryQueryBuilder

    # Get query string
    query = MemoryQueryBuilder.get_by_id()

    # Parse row using column indices
    memory_id = row[MemoryQueryBuilder.Columns.ID]
    content = row[MemoryQueryBuilder.Columns.CONTENT]
"""


class MemoryQueryBuilder:
    """Centralized query builder for Memory operations.

    All Memory-related queries should use this class to ensure
    consistent column ordering and easy maintenance.
    """

    class Columns:
        """Column indices for Memory query results.

        These indices correspond to the RETURN clause order in queries.
        When adding new columns, update both MEMORY_COLUMNS and these indices.

        Standard order (with content):
            id, content, summary, memory_type, created_at, updated_at,
            last_accessed_at, access_count, decay_rate,
            frustration_score, time_cost_hours, context, tags

        Standard order (without content):
            id, summary, memory_type, created_at, updated_at,
            last_accessed_at, access_count, decay_rate,
            frustration_score, time_cost_hours, context, tags
        """

        # With content (include_content=True)
        ID = 0
        CONTENT = 1
        SUMMARY = 2
        MEMORY_TYPE = 3
        CREATED_AT = 4
        UPDATED_AT = 5
        LAST_ACCESSED_AT = 6
        ACCESS_COUNT = 7
        DECAY_RATE = 8
        FRUSTRATION_SCORE = 9
        TIME_COST_HOURS = 10
        CONTEXT = 11
        TAGS = 12

        # Without content offsets (subtract 1 from indices after ID)
        # ID stays at 0, but SUMMARY moves to 1, etc.

    class ColumnsNoContent:
        """Column indices for queries without content field."""

        ID = 0
        SUMMARY = 1
        MEMORY_TYPE = 2
        CREATED_AT = 3
        UPDATED_AT = 4
        LAST_ACCESSED_AT = 5
        ACCESS_COUNT = 6
        DECAY_RATE = 7
        FRUSTRATION_SCORE = 8
        TIME_COST_HOURS = 9
        CONTEXT = 10
        TAGS = 11

    # ==========================================================================
    # Column Definitions (the core of centralization)
    # ==========================================================================

    # Memory node columns (with content)
    MEMORY_COLUMNS = """
        m.id, m.content, m.summary, m.memory_type,
        m.created_at, m.updated_at,
        m.last_accessed_at, m.access_count, m.decay_rate,
        m.frustration_score, m.time_cost_hours
    """.strip()

    # Memory node columns (without content, for search results)
    MEMORY_COLUMNS_NO_CONTENT = """
        m.id, m.summary, m.memory_type,
        m.created_at, m.updated_at,
        m.last_accessed_at, m.access_count, m.decay_rate,
        m.frustration_score, m.time_cost_hours
    """.strip()

    # Sibling memory columns (for explore_related queries)
    SIBLING_COLUMNS = """
        sibling.id, sibling.content, sibling.summary, sibling.memory_type,
        sibling.created_at, sibling.updated_at,
        sibling.last_accessed_at, sibling.access_count, sibling.decay_rate,
        sibling.frustration_score, sibling.time_cost_hours
    """.strip()

    # Linked memory columns (for explore_related linked query)
    LINKED_COLUMNS = """
        linked.id, linked.content, linked.summary, linked.memory_type,
        linked.created_at, linked.updated_at,
        linked.last_accessed_at, linked.access_count, linked.decay_rate,
        linked.frustration_score, linked.time_cost_hours
    """.strip()

    # ==========================================================================
    # Query Methods
    # ==========================================================================

    @classmethod
    def get_by_id(cls) -> str:
        """Query to get a memory by ID with context and tags."""
        return f"""
            MATCH (m:Memory {{id: $id}})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN {cls.MEMORY_COLUMNS},
                   c.name as context, collect(t.name) as tags
        """

    @classmethod
    def list_memories(cls, where_clause: str = "TRUE") -> str:
        """Query to list memories with pagination and filtering."""
        return f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            WHERE {where_clause}
            RETURN {cls.MEMORY_COLUMNS},
                   c.name as context, collect(t.name) as tags
            ORDER BY m.created_at DESC
            SKIP $offset LIMIT $limit
        """

    @classmethod
    def get_memories_by_tag(cls) -> str:
        """Query to get memories with a specific tag."""
        return f"""
            MATCH (m:Memory)-[:TAGGED_WITH]->(t:Tag {{name: $tag}})
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(all_tags:Tag)
            RETURN {cls.MEMORY_COLUMNS},
                   c.name, collect(DISTINCT all_tags.name) as tags
            ORDER BY m.access_count DESC
            LIMIT $limit
        """

    @classmethod
    def get_frequently_accessed(cls) -> str:
        """Query to get frequently accessed memories."""
        return f"""
            MATCH (m:Memory)
            WHERE m.access_count >= $min_count
            OPTIONAL MATCH (m)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (m)-[:TAGGED_WITH]->(t:Tag)
            RETURN {cls.MEMORY_COLUMNS},
                   c.name, collect(t.name) as tags
            ORDER BY m.access_count DESC
            LIMIT $limit
        """

    @classmethod
    def explore_linked(cls) -> str:
        """Query to get directly linked memories."""
        return f"""
            MATCH (m:Memory {{id: $id}})-[r:RELATED_TO]->(linked:Memory)
            OPTIONAL MATCH (linked)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (linked)-[:TAGGED_WITH]->(t:Tag)
            RETURN {cls.LINKED_COLUMNS},
                   c.name, collect(t.name) as tags, r.relation_type, r.reason
            LIMIT $limit
        """

    @classmethod
    def explore_tag_siblings(cls) -> str:
        """Query to get memories sharing tags."""
        return f"""
            MATCH (m:Memory {{id: $id}})-[:TAGGED_WITH]->(t:Tag)<-[:TAGGED_WITH]-(sibling:Memory)
            WHERE m <> sibling
            OPTIONAL MATCH (sibling)-[:ORIGINATED_IN]->(c:Context)
            OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(st:Tag)
            WITH sibling, c, collect(DISTINCT t.name) as shared_tags,
                 collect(DISTINCT st.name) as all_tags
            RETURN {cls.SIBLING_COLUMNS},
                   c.name, all_tags, shared_tags
            ORDER BY size(shared_tags) DESC
            LIMIT $limit
        """

    @classmethod
    def explore_context_siblings(cls) -> str:
        """Query to get memories from same context."""
        return f"""
            MATCH (m:Memory {{id: $id}})-[:ORIGINATED_IN]->(c:Context)<-[:ORIGINATED_IN]-(sibling:Memory)
            WHERE m <> sibling
            OPTIONAL MATCH (sibling)-[:TAGGED_WITH]->(t:Tag)
            RETURN {cls.SIBLING_COLUMNS},
                   c.name, collect(t.name) as tags
            ORDER BY sibling.created_at DESC
            LIMIT $limit
        """


class LinkedMemoryColumns:
    """Column indices for explore_linked query results.

    Additional columns for relation info:
        ..., context, tags, relation_type, reason
    """

    # Same as MemoryQueryBuilder.Columns for memory fields
    ID = 0
    CONTENT = 1
    SUMMARY = 2
    MEMORY_TYPE = 3
    CREATED_AT = 4
    UPDATED_AT = 5
    LAST_ACCESSED_AT = 6
    ACCESS_COUNT = 7
    DECAY_RATE = 8
    FRUSTRATION_SCORE = 9
    TIME_COST_HOURS = 10
    CONTEXT = 11
    TAGS = 12
    RELATION_TYPE = 13
    REASON = 14


class TagSiblingColumns:
    """Column indices for explore_tag_siblings query results.

    Additional column for shared_tags:
        ..., context, all_tags, shared_tags
    """

    ID = 0
    CONTENT = 1
    SUMMARY = 2
    MEMORY_TYPE = 3
    CREATED_AT = 4
    UPDATED_AT = 5
    LAST_ACCESSED_AT = 6
    ACCESS_COUNT = 7
    DECAY_RATE = 8
    FRUSTRATION_SCORE = 9
    TIME_COST_HOURS = 10
    CONTEXT = 11
    ALL_TAGS = 12
    SHARED_TAGS = 13
