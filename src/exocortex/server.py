"""MCP Server definition for Exocortex."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .config import get_config
from .db import get_db
from .models import MemoryType, RelationType

# Configure logging
logger = logging.getLogger(__name__)

# Server instructions for AI agents
SERVER_INSTRUCTIONS = """
Exocortex is your external brain - a local MCP server that stores and retrieves
development insights, technical decisions, and troubleshooting knowledge.

## 🤖 Knowledge Autonomy Mode

Exocortex is designed for AUTONOMOUS knowledge improvement. When you store memories,
the system automatically analyzes them and returns suggestions. **ACT ON THESE SUGGESTIONS**
to continuously improve the knowledge graph.

### After store_memory, check the response for:
1. **suggested_links** - Related memories that should be linked
   → Call `link_memories` with the suggested relation type
2. **insights** - Potential duplicates, contradictions, or improvements
   → Handle based on the insight type:
   - `potential_duplicate`: Consider using `update_memory` instead
   - `potential_contradiction`: Verify and link with `contradicts` or `supersedes`
   - `success_after_failure`: Link with `extends` to document the solution

### Periodic Maintenance
Call `analyze_knowledge` periodically to identify:
- Orphan memories needing tags
- Isolated memories needing links
- Stale memories needing review

## Best Practices for Storing Memories

### Content Structure
When storing memories, structure the content with:
1. **General principle first** - Write the abstract/universal insight
2. **Domain-specific application** - Then add context-specific details
3. **Why it matters** - Explain why this is valuable

Example:
```
## Principle: Cache invalidation on state changes
Always invalidate or update cache atomically with the source of truth.

### Application in E-commerce
For inventory updates, use write-through caching to prevent overselling.

### Why
Users seeing stale inventory leads to failed orders and poor UX.
```

### Tagging Strategy
Always include at least one generic tag for cross-domain discovery:
- Generic: caching, concurrency, performance, architecture, error-handling
- Domain: e-commerce, payment, auth, inventory
- Technology: python, redis, postgresql, fastapi

### Memory Types
- `insight`: Universal patterns and principles (most reusable)
- `decision`: Domain-specific choices with reasoning
- `success`: What worked and why
- `failure`: What failed and lessons learned
- `note`: Raw notes to organize later

### When to Split Memories
If content covers multiple distinct topics, store them separately.
Each memory should be focused on ONE concept for better recall.

## Recalling Memories
Use semantic queries describing your problem, not keywords.
Good: "How to handle cache consistency when updating database"
Bad: "cache database"

## Building the Knowledge Graph

After storing memories, **actively build connections**:
1. When a success resolves a past failure → link with `extends`
2. When new info updates old knowledge → link with `supersedes`
3. When insights are related → link with `related`
4. When a decision is based on an insight → link with `depends_on`
"""

# Initialize FastMCP server
mcp = FastMCP(
    "Exocortex",
    instructions=SERVER_INSTRUCTIONS,
)


# ============================================================================
# Prompts - Templates for AI agents
# ============================================================================


@mcp.prompt()
def recording_guide() -> str:
    """Guide for how to structure and record memories effectively.

    Use this prompt when you want to understand best practices
    for storing knowledge in Exocortex.
    """
    return """
# Exocortex Recording Guide

## Content Structure Template

When recording a memory, use this structure:

```markdown
## [General Principle/Pattern Name]

[1-2 sentences describing the universal insight]

### Context/Application

[How this applies to the specific situation]

### Why This Matters

[The impact or importance of this knowledge]

### Related Concepts

[Optional: connections to other patterns or ideas]
```

## Memory Type Selection

| Situation | Type | Example |
|-----------|------|---------|
| Discovered a reusable pattern | `insight` | "Retry with exponential backoff prevents thundering herd" |
| Made a technical choice | `decision` | "Chose PostgreSQL over MongoDB because..." |
| Solved a problem | `success` | "Fixed N+1 query with eager loading" |
| Something went wrong | `failure` | "Forgot to handle timeout, caused cascade failure" |
| Quick note for later | `note` | "Look into circuit breaker pattern" |

## Tagging Checklist

1. ✅ At least one GENERIC tag (architecture, performance, security, etc.)
2. ✅ Technology tags (python, redis, aws, etc.)
3. ⚪ Domain tags if applicable (e-commerce, fintech, etc.)

## When to Store

Good times to store memories:
- After solving a tricky bug
- After making a technical decision
- After learning something new
- After a code review with insights
- After reading documentation that clarified something

## Examples

### Good Memory (Reusable)
```
Content: "## Principle: Idempotency in API Design

Make write operations idempotent by using client-generated IDs or
idempotency keys. This allows safe retries without side effects.

### Application in Payment Systems
For payment APIs, require an idempotency_key header. Store processed
keys for 24 hours to handle retries.

### Why
Network failures are inevitable. Without idempotency, retries can
cause duplicate charges - a critical bug in payment systems."

Tags: ["api-design", "idempotency", "payment", "reliability"]
Type: insight
```

### Memory to Split (Too Broad)
❌ "Learned about caching and also fixed a bug in auth and reviewed DB schema"
✅ Split into 3 separate memories, each focused on one topic
"""


@mcp.prompt()
def recall_tips() -> str:
    """Tips for effectively recalling memories from Exocortex.

    Use this prompt to learn how to query your external brain effectively.
    """
    return """
# Effective Memory Recall

## Query Strategies

### Describe the Problem, Not Keywords
- ✅ "How to prevent race conditions when updating shared state"
- ❌ "race condition lock"

### Be Specific About Context
- ✅ "Caching strategy for frequently updated data with strong consistency requirements"
- ❌ "caching"

### Use Filters Wisely
- `context_filter`: When you know the project had relevant experience
- `tag_filter`: When you want specific technology insights
- `type_filter`: When you want only failures (to avoid repeating) or decisions (to understand past reasoning)

## Common Recall Patterns

### Before Starting New Feature
```
recall_memories(
    query="[technology] best practices and common pitfalls",
    type_filter="insight"
)
```

### When Debugging
```
recall_memories(
    query="[error description] similar issues",
    type_filter="failure"
)
```

### Understanding Past Decisions
```
recall_memories(
    query="why we chose [technology/pattern]",
    type_filter="decision",
    context_filter="project-name"
)
```
"""


# ============================================================================
# Tools
# ============================================================================


@mcp.tool()
def ping() -> str:
    """Health check tool to verify Exocortex is running.

    Returns a simple message confirming the server is operational.
    """
    config = get_config()
    now = datetime.now(timezone.utc).isoformat()
    return (
        f"🧠 Exocortex is alive!\n"
        f"Time: {now}\n"
        f"Data directory: {config.data_dir}\n"
        f"Embedding model: {config.embedding_model}"
    )


@mcp.tool()
def store_memory(
    content: str,
    context_name: str,
    tags: list[str],
    memory_type: str = "insight",
) -> dict:
    """Store a new memory in Exocortex.

    Use this tool to save development insights, successful solutions,
    failures, technical decisions, or general notes.

    **Best Practices:**
    - Structure content with general principle first, then specific application
    - Include at least one generic tag (e.g., caching, concurrency, architecture)
    - Keep each memory focused on ONE concept
    - Use appropriate memory_type for better organization

    Args:
        content: The content to store (supports Markdown).
                 Recommended structure:
                 1. General principle/pattern
                 2. Specific application context
                 3. Why it matters
        context_name: The project or situation name where this memory originated.
        tags: List of related keywords/tags for categorization.
              Include both generic tags (for cross-domain search) and
              specific tags (technology, domain).
        memory_type: Type of memory - one of: insight, success, failure, decision, note.
                     Default is "insight".

    Returns:
        A dictionary with success status, memory_id, and generated summary.
    """
    try:
        # Validate memory type
        try:
            mem_type = MemoryType(memory_type.lower())
        except ValueError:
            valid_types = [t.value for t in MemoryType]
            return {
                "success": False,
                "error": f"Invalid memory_type '{memory_type}'. Must be one of: {valid_types}",
            }

        db = get_db()
        result = db.store_memory(
            content=content,
            context_name=context_name,
            tags=tags,
            memory_type=mem_type,
        )

        response = {
            "success": result.success,
            "memory_id": result.memory_id,
            "summary": result.summary,
        }

        # Include knowledge autonomy suggestions
        if result.suggested_links:
            response["suggested_links"] = [
                {
                    "target_id": link.target_id,
                    "target_summary": link.target_summary,
                    "similarity": round(link.similarity, 3),
                    "suggested_relation": link.suggested_relation.value,
                    "reason": link.reason,
                }
                for link in result.suggested_links
            ]
            response["link_suggestion_message"] = (
                f"Found {len(result.suggested_links)} related memories. "
                "Consider linking them to build your knowledge graph."
            )

        if result.insights:
            response["insights"] = [
                {
                    "type": insight.insight_type,
                    "message": insight.message,
                    "related_memory_id": insight.related_memory_id,
                    "related_memory_summary": insight.related_memory_summary,
                    "confidence": round(insight.confidence, 3),
                    "suggested_action": insight.suggested_action,
                }
                for insight in result.insights
            ]

        return response

    except ValueError as e:
        # Input validation errors
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("Error storing memory")
        return {"success": False, "error": str(e)}


@mcp.tool()
def recall_memories(
    query: str,
    limit: int = 5,
    context_filter: str | None = None,
    tag_filter: list[str] | None = None,
    type_filter: str | None = None,
) -> dict:
    """Recall relevant memories using semantic search.

    Use this tool to find past experiences, solutions, and insights
    that are relevant to the current problem or question.

    Args:
        query: What you want to recall (describe the problem or topic).
               Use natural language describing your situation, not keywords.
               Good: "How to handle cache consistency when updating database"
               Bad: "cache database"
        limit: Maximum number of memories to return (1-20, default 5).
        context_filter: Optional filter to limit results to a specific project/context.
        tag_filter: Optional list of tags to filter results.
        type_filter: Optional filter by memory type (insight, success, failure, decision, note).

    Returns:
        A dictionary with a list of relevant memories and total count.
    """
    try:
        # Validate limit
        limit = max(1, min(20, limit))

        # Validate type filter
        mem_type_filter = None
        if type_filter:
            try:
                mem_type_filter = MemoryType(type_filter.lower())
            except ValueError:
                valid_types = [t.value for t in MemoryType]
                return {
                    "success": False,
                    "error": f"Invalid type_filter '{type_filter}'. Must be one of: {valid_types}",
                }

        db = get_db()
        memories, total_found = db.recall_memories(
            query=query,
            limit=limit,
            context_filter=context_filter,
            tag_filter=tag_filter,
            type_filter=mem_type_filter,
        )

        return {
            "memories": [
                {
                    "id": m.id,
                    "summary": m.summary,
                    "content": m.content,
                    "type": m.memory_type.value,
                    "similarity": round(m.similarity, 3) if m.similarity else None,
                    "context": m.context,
                    "tags": m.tags,
                    "created_at": m.created_at.isoformat(),
                }
                for m in memories
            ],
            "total_found": total_found,
        }

    except Exception as e:
        logger.exception("Error recalling memories")
        return {"success": False, "error": str(e)}


@mcp.tool()
def list_memories(
    limit: int = 20,
    offset: int = 0,
    context_filter: str | None = None,
    tag_filter: list[str] | None = None,
    type_filter: str | None = None,
) -> dict:
    """List stored memories with pagination.

    Use this tool to browse through all stored memories.

    Args:
        limit: Maximum number of memories to return (1-100, default 20).
        offset: Offset for pagination (default 0).
        context_filter: Optional filter by project/context.
        tag_filter: Optional filter by tags.
        type_filter: Optional filter by memory type.

    Returns:
        A dictionary with memories list, total count, and pagination info.
    """
    try:
        # Validate limit and offset
        limit = max(1, min(100, limit))
        offset = max(0, offset)

        # Validate type filter
        mem_type_filter = None
        if type_filter:
            try:
                mem_type_filter = MemoryType(type_filter.lower())
            except ValueError:
                valid_types = [t.value for t in MemoryType]
                return {
                    "success": False,
                    "error": f"Invalid type_filter '{type_filter}'. Must be one of: {valid_types}",
                }

        db = get_db()
        memories, total_count, has_more = db.list_memories(
            limit=limit,
            offset=offset,
            context_filter=context_filter,
            tag_filter=tag_filter,
            type_filter=mem_type_filter,
        )

        return {
            "memories": [
                {
                    "id": m.id,
                    "summary": m.summary,
                    "type": m.memory_type.value,
                    "context": m.context,
                    "tags": m.tags,
                    "created_at": m.created_at.isoformat(),
                }
                for m in memories
            ],
            "total_count": total_count,
            "has_more": has_more,
        }

    except Exception as e:
        logger.exception("Error listing memories")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_memory(memory_id: str) -> dict:
    """Get a specific memory by its ID.

    Use this tool to retrieve the full content of a specific memory.

    Args:
        memory_id: The unique identifier of the memory to retrieve.

    Returns:
        A dictionary with the full memory details or an error.
    """
    try:
        db = get_db()
        memory = db.get_memory(memory_id)

        if memory is None:
            return {
                "success": False,
                "error": f"Memory with ID '{memory_id}' not found",
            }

        return {
            "success": True,
            "memory": {
                "id": memory.id,
                "content": memory.content,
                "summary": memory.summary,
                "type": memory.memory_type.value,
                "context": memory.context,
                "tags": memory.tags,
                "created_at": memory.created_at.isoformat(),
                "updated_at": memory.updated_at.isoformat(),
            },
        }

    except Exception as e:
        logger.exception("Error getting memory")
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_memory(memory_id: str) -> dict:
    """Delete a memory by its ID.

    Use this tool to remove incorrect or outdated memories.

    Args:
        memory_id: The unique identifier of the memory to delete.

    Returns:
        A dictionary indicating success or failure.
    """
    try:
        db = get_db()
        deleted = db.delete_memory(memory_id)

        if not deleted:
            return {
                "success": False,
                "error": f"Memory with ID '{memory_id}' not found",
            }

        return {
            "success": True,
            "deleted_id": memory_id,
        }

    except Exception as e:
        logger.exception("Error deleting memory")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_stats() -> dict:
    """Get statistics about stored memories.

    Use this tool to understand the state of your external brain.

    Returns:
        A dictionary with statistics including total memories,
        breakdown by type, number of contexts and tags.
    """
    try:
        db = get_db()
        stats = db.get_stats()

        return {
            "total_memories": stats.total_memories,
            "memories_by_type": stats.memories_by_type,
            "total_contexts": stats.total_contexts,
            "total_tags": stats.total_tags,
            "top_tags": stats.top_tags,
        }

    except Exception as e:
        logger.exception("Error getting stats")
        return {"success": False, "error": str(e)}


# ============================================================================
# Advanced Tools - Memory Links, Updates, Graph Exploration
# ============================================================================


@mcp.tool()
def link_memories(
    source_id: str,
    target_id: str,
    relation_type: str,
    reason: str | None = None,
) -> dict:
    """Create a link between two memories.

    Use this tool to explicitly connect related memories, creating
    a knowledge graph that can be traversed later.

    Args:
        source_id: The ID of the source memory.
        target_id: The ID of the target memory to link to.
        relation_type: Type of relationship. One of:
            - "related": Generally related memories
            - "supersedes": Source updates/replaces target
            - "contradicts": Source contradicts target
            - "extends": Source extends/elaborates target
            - "depends_on": Source depends on target
        reason: Optional explanation for why these memories are linked.

    Returns:
        A dictionary indicating success or failure.
    """
    try:
        # Validate relation type
        try:
            rel_type = RelationType(relation_type.lower())
        except ValueError:
            valid_types = [t.value for t in RelationType]
            return {
                "success": False,
                "error": f"Invalid relation_type '{relation_type}'. Must be one of: {valid_types}",
            }

        db = get_db()
        success, message = db.link_memories(
            source_id=source_id,
            target_id=target_id,
            relation_type=rel_type,
            reason=reason,
        )

        if not success:
            return {
                "success": False,
                "error": message,
            }

        return {
            "success": True,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": rel_type.value,
            "message": message,
        }

    except Exception as e:
        logger.exception("Error linking memories")
        return {"success": False, "error": str(e)}


@mcp.tool()
def unlink_memories(source_id: str, target_id: str) -> dict:
    """Remove a link between two memories.

    Args:
        source_id: The ID of the source memory.
        target_id: The ID of the target memory.

    Returns:
        A dictionary indicating success or failure.
    """
    try:
        db = get_db()
        success = db.unlink_memories(source_id, target_id)

        if not success:
            return {
                "success": False,
                "error": "Link not found between these memories",
            }

        return {
            "success": True,
            "source_id": source_id,
            "target_id": target_id,
        }

    except Exception as e:
        logger.exception("Error unlinking memories")
        return {"success": False, "error": str(e)}


@mcp.tool()
def update_memory(
    memory_id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    memory_type: str | None = None,
) -> dict:
    """Update an existing memory.

    Use this tool to modify a memory's content, tags, or type.
    When content is updated, the embedding is automatically regenerated.

    Args:
        memory_id: The ID of the memory to update.
        content: New content (optional). Updates embedding and summary.
        tags: New tags (optional). Replaces all existing tags.
        memory_type: New memory type (optional).

    Returns:
        A dictionary with success status and list of changes made.
    """
    try:
        # Validate memory type if provided
        mem_type = None
        if memory_type:
            try:
                mem_type = MemoryType(memory_type.lower())
            except ValueError:
                valid_types = [t.value for t in MemoryType]
                return {
                    "success": False,
                    "error": f"Invalid memory_type '{memory_type}'. Must be one of: {valid_types}",
                }

        db = get_db()
        success, changes = db.update_memory(
            memory_id=memory_id,
            content=content,
            tags=tags,
            memory_type=mem_type,
        )

        if not success:
            return {
                "success": False,
                "error": f"Memory with ID '{memory_id}' not found",
            }

        # Get updated memory for summary
        memory = db.get_memory(memory_id)

        return {
            "success": True,
            "memory_id": memory_id,
            "changes": changes,
            "summary": memory.summary if memory else "",
        }

    except Exception as e:
        logger.exception("Error updating memory")
        return {"success": False, "error": str(e)}


@mcp.tool()
def explore_related(
    memory_id: str,
    include_tag_siblings: bool = True,
    include_context_siblings: bool = True,
    max_per_category: int = 5,
) -> dict:
    """Explore memories related to a given memory through graph traversal.

    Use this tool to discover connections between memories:
    - Directly linked memories (via link_memories)
    - Memories sharing the same tags
    - Memories in the same context/project

    This is useful for building a broader understanding of a topic
    by finding related knowledge you may have forgotten about.

    Args:
        memory_id: The ID of the memory to explore from.
        include_tag_siblings: Include memories with shared tags (default: True).
        include_context_siblings: Include memories in same context (default: True).
        max_per_category: Maximum memories per category (default: 5).

    Returns:
        A dictionary with related memories grouped by relationship type.
    """
    try:
        db = get_db()

        # First verify the memory exists
        center_memory = db.get_memory(memory_id)
        if center_memory is None:
            return {
                "success": False,
                "error": f"Memory with ID '{memory_id}' not found",
            }

        # Get related memories
        related = db.explore_related(
            memory_id=memory_id,
            include_tag_siblings=include_tag_siblings,
            include_context_siblings=include_context_siblings,
            max_per_category=max_per_category,
        )

        def format_memory(m):
            return {
                "id": m.id,
                "summary": m.summary,
                "type": m.memory_type.value,
                "context": m.context,
                "tags": m.tags,
                "created_at": m.created_at.isoformat(),
            }

        return {
            "center_memory": {
                "id": center_memory.id,
                "summary": center_memory.summary,
                "type": center_memory.memory_type.value,
                "context": center_memory.context,
                "tags": center_memory.tags,
            },
            "linked": [format_memory(m) for m in related["linked"]],
            "by_tag": [format_memory(m) for m in related["by_tag"]],
            "by_context": [format_memory(m) for m in related["by_context"]],
            "total_related": (
                len(related["linked"])
                + len(related["by_tag"])
                + len(related["by_context"])
            ),
        }

    except Exception as e:
        logger.exception("Error exploring related memories")
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_memory_links(memory_id: str) -> dict:
    """Get all outgoing links from a memory.

    Args:
        memory_id: The ID of the memory.

    Returns:
        A dictionary with the list of links from this memory.
    """
    try:
        db = get_db()

        # Verify memory exists
        memory = db.get_memory(memory_id)
        if memory is None:
            return {
                "success": False,
                "error": f"Memory with ID '{memory_id}' not found",
            }

        links = db.get_memory_links(memory_id)

        return {
            "success": True,
            "memory_id": memory_id,
            "links": [
                {
                    "target_id": link.target_id,
                    "target_summary": link.target_summary,
                    "relation_type": link.relation_type.value,
                    "reason": link.reason,
                    "created_at": link.created_at.isoformat() if link.created_at else None,
                }
                for link in links
            ],
            "total_links": len(links),
        }

    except Exception as e:
        logger.exception("Error getting memory links")
        return {"success": False, "error": str(e)}


@mcp.tool()
def analyze_knowledge() -> dict:
    """Analyze the knowledge base for health issues and improvement opportunities.

    Use this tool periodically to maintain knowledge quality.
    It identifies:
    - Orphan memories (no tags)
    - Low connectivity (few links between memories)
    - Stale memories (not updated in a long time)
    - Similar tags that might need normalization
    - General health score and improvement suggestions

    Returns:
        A dictionary with health score, issues, and suggestions.
    """
    try:
        db = get_db()
        result = db.analyze_knowledge()

        return {
            "success": True,
            "total_memories": result.total_memories,
            "health_score": round(result.health_score, 1),
            "issues": [
                {
                    "type": issue.issue_type,
                    "severity": issue.severity,
                    "message": issue.message,
                    "affected_memory_ids": issue.affected_memory_ids[:5],  # Limit for readability
                    "suggested_action": issue.suggested_action,
                }
                for issue in result.issues
            ],
            "suggestions": result.suggestions,
            "stats": result.stats,
        }

    except Exception as e:
        logger.exception("Error analyzing knowledge")
        return {"success": False, "error": str(e)}


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp
