"""MCP Server for Exocortex."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .container import get_container
from .domain.exceptions import (
    DuplicateLinkError,
    MemoryNotFoundError,
    SelfLinkError,
    ValidationError,
)
from .domain.models import MemoryType, RelationType

logger = logging.getLogger(__name__)

# =============================================================================
# Server Instructions
# =============================================================================

SERVER_INSTRUCTIONS = """\
Exocortex is your external brain - a persistent knowledge store for development insights.

## 🎯 Proactive Knowledge Capture

**IMPORTANT**: Actively propose storing valuable insights during conversations!

### When to Suggest Recording
- After debugging a tricky issue → "This debugging insight could be valuable. Want me to store it?"
- When discovering a useful pattern → "This pattern might help in future projects. Should I record it?"
- After architectural discussions → "This decision has good reasoning. Let me save it for reference."
- When a solution is found after multiple attempts → "The solution and failed approaches are worth remembering."
- After explaining something complex → "This explanation could help next time. Want me to store it?"

### How to Propose
1. Summarize the key insight in 1-2 sentences
2. Suggest appropriate tags and memory type
3. Ask if the user wants to store it (or just do it if clearly valuable)

Example:
> "We just solved a tricky async/await issue with connection pooling.
> This would make a good `success` memory with tags [async, database, connection-pool].
> Should I store this for future reference?"

## Best Practices for Storing Memories

1. **Content Structure**: Write clear, actionable content. Use Markdown.
   - Bad: "Fixed bug"
   - Good: "## Database Connection Pooling Fix\\n\\nProblem: Connections exhausted...\\nSolution: Implemented..."

2. **Tagging Strategy**: Use hierarchical, reusable tags.
   - General: python, database, performance, security
   - Specific: sqlalchemy, postgresql, async

3. **Memory Types**:
   - `insight`: General learnings and patterns
   - `success`: Solutions that worked
   - `failure`: What didn't work and why
   - `decision`: Technical decisions with reasoning
   - `note`: Quick references

4. **Splitting Content**: One memory = one concept. Split multi-topic content.

## Knowledge Autonomy Mode

After storing a memory:
- Check `suggested_links` for related memories to link
- Review `insights` for potential duplicates or contradictions
- Act on these suggestions to improve knowledge quality

Use `exo_analyze_knowledge` periodically to maintain knowledge base health.
"""

# =============================================================================
# Server Setup
# =============================================================================

mcp = FastMCP(
    "exocortex",
    instructions=SERVER_INSTRUCTIONS,
)


# =============================================================================
# Prompts
# =============================================================================


@mcp.prompt()
def recording_guide() -> str:
    """Guide for recording development insights effectively."""
    return """\
# Recording Development Insights

## When to Record
- After solving a tricky bug
- When learning something new
- After making an architectural decision
- When finding a useful pattern or anti-pattern
- After a failed approach (equally valuable!)

## What to Include

### For Insights
```markdown
## [Short Title]

**Context**: [When/where this applies]

**The Pattern/Learning**: [Core insight]

**Example**: [Concrete example if applicable]

**Caveats**: [When this might not apply]
```

### For Decisions
```markdown
## Decision: [What was decided]

**Options Considered**:
1. [Option A] - [Pros/Cons]
2. [Option B] - [Pros/Cons]

**Chosen**: [Which option and why]

**Trade-offs Accepted**: [What we gave up]
```

## Tagging Guidelines
- Use 3-7 tags per memory
- Mix general (python, database) and specific (sqlalchemy, postgresql)
- Include problem domain (auth, caching, performance)
"""


@mcp.prompt()
def recall_tips() -> str:
    """Tips for effective memory recall."""
    return """\
# Effective Memory Recall

## Search Strategies

1. **Describe the Problem**: "How to handle database connection timeouts"
2. **Use Similar Concepts**: "connection pool exhaustion" instead of "too many connections"
3. **Include Context**: Add project or technology context when filtering

## Filters for Precision
- `context_filter`: Limit to specific project
- `tag_filter`: Focus on specific topics
- `type_filter`: Find only successes, failures, etc.

## After Finding Memories
- Use `exo_explore_related` to discover connected knowledge
- Check for more recent updates via links
"""


# =============================================================================
# Basic Tools
# =============================================================================


@mcp.tool(name="exo_ping")
def ping() -> dict[str, Any]:
    """Health check - verify Exocortex is running.

    Returns a simple message confirming the server is operational.
    """
    return {"status": "ok", "message": "Exocortex is operational"}


@mcp.tool(name="exo_store_memory")
def store_memory(
    content: str,
    context_name: str,
    tags: list[str],
    memory_type: str = "insight",
) -> dict[str, Any]:
    """Store a new memory in Exocortex.

    Use this to save development insights, solutions, failures,
    technical decisions, or notes.

    Args:
        content: The content to store (supports Markdown).
        context_name: The project or situation name.
        tags: List of related keywords/tags for categorization.
        memory_type: Type of memory (insight, success, failure, decision, note).

    Returns:
        Success status, memory_id, summary, suggested_links, and insights.
    """
    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        mem_type = MemoryType.INSIGHT

    container = get_container()

    try:
        result = container.memory_service.store_memory(
            content=content,
            context_name=context_name,
            tags=tags,
            memory_type=mem_type,
            auto_analyze=True,
        )

        return {
            "success": result.success,
            "memory_id": result.memory_id,
            "summary": result.summary,
            "suggested_links": [
                {
                    "target_id": link.target_id,
                    "target_summary": link.target_summary,
                    "similarity": round(link.similarity, 3),
                    "suggested_relation": link.suggested_relation.value,
                    "reason": link.reason,
                }
                for link in result.suggested_links
            ],
            "insights": [
                {
                    "type": insight.insight_type,
                    "message": insight.message,
                    "related_memory_id": insight.related_memory_id,
                    "confidence": round(insight.confidence, 3),
                    "suggested_action": insight.suggested_action,
                }
                for insight in result.insights
            ],
        }
    except ValidationError as e:
        return {"success": False, "error": str(e)}


@mcp.tool(name="exo_recall_memories")
def recall_memories(
    query: str,
    limit: int = 5,
    context_filter: str | None = None,
    tag_filter: list[str] | None = None,
    type_filter: str | None = None,
) -> dict[str, Any]:
    """Recall relevant memories using semantic search.

    Use this to find past experiences, solutions, and insights
    relevant to the current problem.

    Args:
        query: What you want to recall (describe the problem or topic).
        limit: Maximum number of memories to return (1-20).
        context_filter: Optional filter by project/context.
        tag_filter: Optional filter by tags.
        type_filter: Optional filter by memory type.

    Returns:
        List of relevant memories and total count.
    """
    limit = min(max(1, limit), 20)

    mem_type = None
    if type_filter:
        with contextlib.suppress(ValueError):
            mem_type = MemoryType(type_filter)

    container = get_container()
    memories, total_found = container.memory_service.recall_memories(
        query=query,
        limit=limit,
        context_filter=context_filter,
        tag_filter=tag_filter,
        type_filter=mem_type,
    )

    return {
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "summary": m.summary,
                "memory_type": m.memory_type.value,
                "context": m.context,
                "tags": m.tags,
                "similarity": round(m.similarity, 3) if m.similarity else None,
                "created_at": m.created_at.isoformat(),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in memories
        ],
        "total_found": total_found,
    }


@mcp.tool(name="exo_list_memories")
def list_memories(
    limit: int = 20,
    offset: int = 0,
    context_filter: str | None = None,
    tag_filter: list[str] | None = None,
    type_filter: str | None = None,
) -> dict[str, Any]:
    """List stored memories with pagination.

    Use this to browse through all stored memories.

    Args:
        limit: Maximum number of memories to return (1-100).
        offset: Offset for pagination.
        context_filter: Optional filter by project/context.
        tag_filter: Optional filter by tags.
        type_filter: Optional filter by memory type.

    Returns:
        List of memories, total count, and pagination info.
    """
    limit = min(max(1, limit), 100)
    offset = max(0, offset)

    mem_type = None
    if type_filter:
        with contextlib.suppress(ValueError):
            mem_type = MemoryType(type_filter)

    container = get_container()
    memories, total_count, has_more = container.memory_service.list_memories(
        limit=limit,
        offset=offset,
        context_filter=context_filter,
        tag_filter=tag_filter,
        type_filter=mem_type,
    )

    return {
        "memories": [
            {
                "id": m.id,
                "summary": m.summary,
                "memory_type": m.memory_type.value,
                "context": m.context,
                "tags": m.tags,
                "created_at": m.created_at.isoformat(),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in memories
        ],
        "total_count": total_count,
        "has_more": has_more,
        "limit": limit,
        "offset": offset,
    }


@mcp.tool(name="exo_get_memory")
def get_memory(memory_id: str) -> dict[str, Any]:
    """Get a specific memory by its ID.

    Use this to retrieve the full content of a specific memory.

    Args:
        memory_id: The unique identifier of the memory.

    Returns:
        Full memory details or error.
    """
    container = get_container()
    memory = container.memory_service.get_memory(memory_id)

    if memory is None:
        return {"success": False, "error": f"Memory '{memory_id}' not found"}

    return {
        "success": True,
        "memory": {
            "id": memory.id,
            "content": memory.content,
            "summary": memory.summary,
            "memory_type": memory.memory_type.value,
            "context": memory.context,
            "tags": memory.tags,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
        },
    }


@mcp.tool(name="exo_delete_memory")
def delete_memory(memory_id: str) -> dict[str, Any]:
    """Delete a memory by its ID.

    Use this to remove incorrect or outdated memories.

    Args:
        memory_id: The unique identifier of the memory to delete.

    Returns:
        Success status.
    """
    container = get_container()
    success = container.memory_service.delete_memory(memory_id)

    if not success:
        return {"success": False, "error": f"Memory '{memory_id}' not found"}

    return {"success": True, "message": f"Memory '{memory_id}' deleted"}


@mcp.tool(name="exo_get_stats")
def get_stats() -> dict[str, Any]:
    """Get statistics about stored memories.

    Use this to understand the state of your external brain.

    Returns:
        Statistics including total memories, breakdown by type,
        number of contexts and tags.
    """
    container = get_container()
    stats = container.memory_service.get_stats()

    return {
        "total_memories": stats.total_memories,
        "memories_by_type": stats.memories_by_type,
        "total_contexts": stats.total_contexts,
        "total_tags": stats.total_tags,
        "top_tags": stats.top_tags,
    }


# =============================================================================
# Advanced Tools
# =============================================================================


@mcp.tool(name="exo_link_memories")
def link_memories(
    source_id: str,
    target_id: str,
    relation_type: str = "related",
    reason: str | None = None,
) -> dict[str, Any]:
    """Create a relationship between two memories.

    Use this to build a knowledge graph connecting related memories.

    Args:
        source_id: Source memory ID (the memory that has the relationship).
        target_id: Target memory ID (the memory being related to).
        relation_type: Type of relationship (related, supersedes, contradicts, extends, depends_on).
        reason: Optional reason for the link.

    Returns:
        Success status and message.
    """
    try:
        rel_type = RelationType(relation_type)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid relation type. Valid types: {[r.value for r in RelationType]}",
        }

    container = get_container()

    try:
        container.memory_service.link_memories(
            source_id=source_id,
            target_id=target_id,
            relation_type=rel_type,
            reason=reason,
        )
        return {
            "success": True,
            "message": f"Linked '{source_id}' -> '{target_id}' ({relation_type})",
        }
    except SelfLinkError:
        return {"success": False, "error": "Cannot link a memory to itself"}
    except MemoryNotFoundError as e:
        return {"success": False, "error": str(e)}
    except DuplicateLinkError as e:
        return {
            "success": False,
            "error": f"Link already exists with type '{e.existing_type}'",
        }


@mcp.tool(name="exo_unlink_memories")
def unlink_memories(source_id: str, target_id: str) -> dict[str, Any]:
    """Remove a relationship between two memories.

    Args:
        source_id: Source memory ID.
        target_id: Target memory ID.

    Returns:
        Success status.
    """
    container = get_container()
    success = container.memory_service.unlink_memories(source_id, target_id)

    if not success:
        return {"success": False, "error": "Link not found"}

    return {"success": True, "message": "Link removed"}


@mcp.tool(name="exo_get_memory_links")
def get_memory_links(memory_id: str) -> dict[str, Any]:
    """Get all outgoing links from a memory.

    Args:
        memory_id: The memory ID to get links for.

    Returns:
        List of links with target memory info.
    """
    container = get_container()
    links = container.memory_service.get_memory_links(memory_id)

    return {
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
        "count": len(links),
    }


@mcp.tool(name="exo_update_memory")
def update_memory(
    memory_id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    memory_type: str | None = None,
) -> dict[str, Any]:
    """Update an existing memory.

    Use this to modify content, tags, or type of an existing memory.

    Args:
        memory_id: The memory ID to update.
        content: New content (optional).
        tags: New tags (optional, replaces existing).
        memory_type: New memory type (optional).

    Returns:
        Success status, updated summary, and list of changes.
    """
    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            return {"success": False, "error": f"Invalid memory type: {memory_type}"}

    container = get_container()
    success, changes, summary = container.memory_service.update_memory(
        memory_id=memory_id,
        content=content,
        tags=tags,
        memory_type=mem_type,
    )

    if not success:
        return {"success": False, "error": f"Memory '{memory_id}' not found"}

    return {
        "success": True,
        "memory_id": memory_id,
        "summary": summary,
        "changes": changes,
    }


@mcp.tool(name="exo_explore_related")
def explore_related(
    memory_id: str,
    include_tag_siblings: bool = True,
    include_context_siblings: bool = True,
    max_per_category: int = 5,
) -> dict[str, Any]:
    """Explore memories related to a given memory.

    Uses graph traversal to find memories that are:
    - Directly linked via RELATED_TO
    - Share tags (tag siblings)
    - Share context (context siblings)

    Args:
        memory_id: The memory ID to explore from.
        include_tag_siblings: Include memories sharing tags.
        include_context_siblings: Include memories from same context.
        max_per_category: Max memories per category.

    Returns:
        Related memories grouped by relationship type.
    """
    container = get_container()

    result = container.memory_service.explore_related(
        memory_id=memory_id,
        include_tag_siblings=include_tag_siblings,
        include_context_siblings=include_context_siblings,
        max_per_category=max_per_category,
    )

    def format_memory(m):
        return {
            "id": m.id,
            "summary": m.summary,
            "memory_type": m.memory_type.value,
            "context": m.context,
            "tags": m.tags,
            "created_at": m.created_at.isoformat(),
        }

    return {
        "success": True,
        "source_memory_id": memory_id,
        "linked": [format_memory(m) for m in result.get("linked", [])],
        "by_tag": [format_memory(m) for m in result.get("by_tag", [])],
        "by_context": [format_memory(m) for m in result.get("by_context", [])],
        "total_found": sum(len(v) for v in result.values()),
    }


@mcp.tool(name="exo_analyze_knowledge")
def analyze_knowledge() -> dict[str, Any]:
    """Analyze the knowledge base for health and improvement opportunities.

    Checks for:
    - Orphan memories (no tags)
    - Unlinked memories (no relationships)
    - Stale memories (not updated in 90+ days)
    - Low connectivity

    Returns:
        Health score, issues found, and improvement suggestions.
    """
    container = get_container()
    result = container.memory_service.analyze_knowledge()

    return {
        "total_memories": result.total_memories,
        "health_score": round(result.health_score, 1),
        "issues": [
            {
                "type": issue.issue_type,
                "severity": issue.severity,
                "message": issue.message,
                "affected_count": len(issue.affected_memory_ids),
                "affected_memory_ids": issue.affected_memory_ids[:5],
                "suggested_action": issue.suggested_action,
            }
            for issue in result.issues
        ],
        "suggestions": result.suggestions,
        "stats": result.stats,
    }
