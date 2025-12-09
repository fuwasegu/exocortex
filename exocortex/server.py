"""MCP Server for Exocortex."""

from __future__ import annotations

import contextlib
import json
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
# Helper Functions
# =============================================================================


def _normalize_content(content: str) -> str:
    """Normalize content that may be wrapped in MCP TextContent format.

    Some MCP clients send content as JSON array: [{"text": "...", "type": "text"}]
    This function extracts the actual text content.

    Args:
        content: The content string, possibly JSON-encoded.

    Returns:
        The normalized plain text content.
    """
    if not content:
        return content

    # Check if it looks like JSON array
    stripped = content.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return content

    try:
        data = json.loads(stripped)
        if isinstance(data, list) and len(data) > 0:
            # Extract text from first element
            first = data[0]
            if isinstance(first, dict) and "text" in first:
                inner_text = first["text"]
                # Recursively normalize in case of double-encoding
                return _normalize_content(inner_text)
        return content
    except (json.JSONDecodeError, TypeError, KeyError):
        return content


def _format_memory_full(memory, include_pain: bool = False) -> dict[str, Any]:
    """Format a memory with full details for API response.

    Args:
        memory: MemoryWithContext instance.
        include_pain: Whether to include frustration/pain indicators.

    Returns:
        Dictionary with memory details.
    """
    result = {
        "id": memory.id,
        "content": memory.content,
        "summary": memory.summary,
        "memory_type": memory.memory_type.value,
        "context": memory.context,
        "tags": memory.tags,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
    }

    if include_pain:
        from exocortex.brain.amygdala import FrustrationIndexer

        indexer = FrustrationIndexer()
        result["similarity"] = (
            round(memory.similarity, 3) if memory.similarity else None
        )
        result["frustration_score"] = (
            round(memory.frustration_score, 3) if memory.frustration_score else 0.0
        )
        result["pain_indicator"] = indexer.get_pain_emoji(
            memory.frustration_score or 0.0
        )
        result["time_cost_hours"] = memory.time_cost_hours

    return result


def _format_memory_brief(memory) -> dict[str, Any]:
    """Format a memory with brief details for list/explore responses.

    Args:
        memory: MemoryWithContext instance.

    Returns:
        Dictionary with brief memory details.
    """
    return {
        "id": memory.id,
        "summary": memory.summary,
        "memory_type": memory.memory_type.value,
        "context": memory.context,
        "tags": memory.tags,
        "created_at": memory.created_at.isoformat(),
    }


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

## 🧠 MANDATORY: Post-Storage Memory Consolidation

**Like human sleep consolidates memories, you MUST organize after storing.**

When `exo_store_memory` returns successfully, ALWAYS perform these steps:

### Step 1: Link Related Memories
Check the `suggested_links` in the response. For each suggestion with similarity > 0.7:
- Call `exo_link_memories` to create the relationship
- Use the suggested relation type

### Step 2: Handle Insights
Check the `insights` in the response:
- **duplicate_candidate**: Consider if the new memory should supersede the old one
- **potential_contradiction**: Review and resolve with `supersedes` or `contradicts` link
- **knowledge_gap**: Note for future learning

### Step 3: Periodic Health Check
If `should_analyze` is true in the response:
- Call `exo_analyze_knowledge` to check overall health
- Address any issues found (orphan memories, unlinked memories, etc.)

**This consolidation is NOT optional. Skipping it degrades knowledge quality over time.**

Example flow:
```
1. User: "Remember this pattern"
2. You: Call exo_store_memory → get suggested_links + insights
3. You: Call exo_link_memories for high-similarity suggestions
4. You: Report to user: "Stored and linked to 2 related memories"
```
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
# Health Check Tools
# =============================================================================


@mcp.tool(name="exo_ping")
def ping() -> dict[str, Any]:
    """Health check - verify Exocortex is running.

    Returns a simple message confirming the server is operational.
    """
    return {"status": "ok", "message": "Exocortex is operational"}


# =============================================================================
# Memory CRUD Tools
# =============================================================================


@mcp.tool(name="exo_store_memory")
def store_memory(
    content: str,
    context_name: str,
    tags: list[str],
    memory_type: str = "insight",
    is_painful: bool | None = None,
    time_cost_hours: float | None = None,
) -> dict[str, Any]:
    """Store a new memory in Exocortex.

    Use this to save development insights, solutions, failures,
    technical decisions, or notes.

    **IMPORTANT**: After storing, you MUST process the returned `next_actions`
    to consolidate the knowledge base. This is like how sleep consolidates
    human memory - it's essential for knowledge quality.

    Args:
        content: The content to store (supports Markdown).
        context_name: The project or situation name.
        tags: List of related keywords/tags for categorization.
        memory_type: Type of memory (insight, success, failure, decision, note).
        is_painful: Mark as a frustrating/painful memory (boosts priority in recall).
            Based on Somatic Marker Hypothesis - painful memories are prioritized.
        time_cost_hours: Time spent on this problem (hours). Used for frustration scoring.

    Returns:
        Success status, memory_id, summary, suggested_links, insights,
        and next_actions that MUST be executed for memory consolidation.
    """
    # Normalize content in case it's wrapped in MCP TextContent format
    normalized_content = _normalize_content(content)

    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        mem_type = MemoryType.INSIGHT

    container = get_container()

    try:
        result = container.memory_service.store_memory(
            content=normalized_content,
            context_name=context_name,
            tags=tags,
            memory_type=mem_type,
            auto_analyze=True,
            is_painful=is_painful,
            time_cost_hours=time_cost_hours,
        )

        # Build next_actions for memory consolidation
        next_actions = []

        # Action 1: Link high-similarity memories
        high_similarity_links = [
            link for link in result.suggested_links if link.similarity >= 0.7
        ]
        if high_similarity_links:
            next_actions.append(
                {
                    "action": "link_memories",
                    "priority": "high",
                    "description": f"Link to {len(high_similarity_links)} related memories",
                    "details": [
                        {
                            "call": "exo_link_memories",
                            "args": {
                                "source_id": result.memory_id,
                                "target_id": link.target_id,
                                "relation_type": link.suggested_relation.value,
                                "reason": link.reason,
                            },
                        }
                        for link in high_similarity_links
                    ],
                }
            )

        # Action 2: Handle insights (duplicates, contradictions)
        critical_insights = [
            i
            for i in result.insights
            if i.insight_type in ("duplicate_candidate", "potential_contradiction")
        ]
        if critical_insights:
            next_actions.append(
                {
                    "action": "review_insights",
                    "priority": "medium",
                    "description": "Review potential duplicates or contradictions",
                    "details": [
                        {
                            "type": insight.insight_type,
                            "message": insight.message,
                            "related_id": insight.related_memory_id,
                            "suggested_action": insight.suggested_action,
                        }
                        for insight in critical_insights
                    ],
                }
            )

        # Action 3: Periodic health check (every 10 memories or on issues)
        stats = container.memory_service.get_stats()
        total_memories = stats.total_memories
        should_analyze = (
            total_memories % 10 == 0  # Every 10 memories
            or len(critical_insights) > 0  # On critical insights
        )

        if should_analyze:
            next_actions.append(
                {
                    "action": "analyze_health",
                    "priority": "low",
                    "description": "Run knowledge base health check",
                    "details": {"call": "exo_analyze_knowledge"},
                }
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
            # New fields for memory consolidation
            "next_actions": next_actions,
            "consolidation_required": len(next_actions) > 0,
            "consolidation_message": (
                f"🧠 Memory stored. {len(next_actions)} consolidation action(s) required."
                if next_actions
                else "✅ Memory stored. No consolidation needed."
            ),
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
        "memories": [_format_memory_full(m, include_pain=True) for m in memories],
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
                **_format_memory_brief(m),
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
        "memory": _format_memory_full(memory),
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


# =============================================================================
# Statistics Tools
# =============================================================================


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
# Link & Relationship Tools
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
    # Normalize content in case it's wrapped in MCP TextContent format
    normalized_content = _normalize_content(content) if content else None

    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            return {"success": False, "error": f"Invalid memory type: {memory_type}"}

    container = get_container()
    success, changes, summary = container.memory_service.update_memory(
        memory_id=memory_id,
        content=normalized_content,
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

    return {
        "success": True,
        "source_memory_id": memory_id,
        "linked": [_format_memory_brief(m) for m in result.get("linked", [])],
        "by_tag": [_format_memory_brief(m) for m in result.get("by_tag", [])],
        "by_context": [_format_memory_brief(m) for m in result.get("by_context", [])],
        "total_found": sum(len(v) for v in result.values()),
    }


# =============================================================================
# Temporal Reasoning Tools (Phase 2.3)
# =============================================================================


@mcp.tool(name="exo_trace_lineage")
def trace_lineage(
    memory_id: str,
    direction: str = "backward",
    relation_types: list[str] | None = None,
    max_depth: int = 10,
) -> dict[str, Any]:
    """Trace the lineage/history of a memory through temporal relationships.

    Follow relationships like EVOLVED_FROM, CAUSED_BY, REJECTED_BECAUSE
    to understand how decisions and code evolved over time.

    This enables "causal reasoning" - understanding WHY something became
    the way it is by tracing its history.

    Args:
        memory_id: Starting memory ID to trace from.
        direction: "backward" to find ancestors (what this evolved from),
                   "forward" to find descendants (what evolved from this).
        relation_types: List of relation types to follow. Defaults to:
                       ["evolved_from", "caused_by", "rejected_because", "supersedes"]
        max_depth: Maximum traversal depth (default: 10).

    Returns:
        Lineage chain with each node containing:
        - id, summary, memory_type, created_at
        - depth: distance from starting node
        - relation_type: how it relates to parent
        - reason: why the relationship exists

    Example usage:
        - "Why did we choose this architecture?" → trace_lineage(current_decision, "backward")
        - "What problems did this change cause?" → trace_lineage(change_id, "forward")
    """
    container = get_container()

    # Use repository directly for lineage tracing
    lineage = container.repository.trace_lineage(
        memory_id=memory_id,
        direction=direction,
        relation_types=relation_types,
        max_depth=max_depth,
    )

    # Get the starting memory info
    start_memory = container.repository.get_by_id(memory_id)
    start_info = None
    if start_memory:
        start_info = {
            "id": start_memory.id,
            "summary": start_memory.summary,
            "memory_type": start_memory.memory_type.value,
            "created_at": start_memory.created_at.isoformat(),
        }

    return {
        "success": True,
        "start_memory": start_info,
        "direction": direction,
        "lineage": lineage,
        "total_nodes": len(lineage),
        "max_depth_reached": max(node["depth"] for node in lineage) if lineage else 0,
    }


# =============================================================================
# Analytics & Health Tools
# =============================================================================


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


# =============================================================================
# Background Processing Tools
# =============================================================================


@mcp.tool(name="exo_sleep")
def sleep(enable_logging: bool = False) -> dict[str, Any]:
    """Trigger background consolidation process (Sleep/Dream mechanism).

    Spawns a detached worker process that:
    1. Deduplication: Detect and link highly similar memories (similarity >= 95%)
    2. Orphan Rescue: Find isolated memories and link to related ones
    3. Pattern Mining: (Phase 2) Extract patterns from frequently accessed topics

    Use this when:
    - A task is completed
    - Before ending the session
    - After storing many memories at once

    The worker runs in the background and does NOT block this call.
    If the database is in use, the worker will wait or exit gracefully.

    Args:
        enable_logging: If True, worker logs are written to ~/.exocortex/logs/dream.log

    Returns:
        Status indicating whether the worker was spawned.
    """
    from .config import get_config
    from .worker.process import (
        get_default_log_path,
        is_dreamer_running,
        spawn_detached_dreamer,
    )

    config = get_config()
    lock_path = config.data_dir / "dream.lock"

    # Check if a worker is already running
    if is_dreamer_running(lock_path):
        return {
            "success": True,
            "message": "Dream worker is already running",
            "status": "already_running",
        }

    # Spawn the worker
    log_path = get_default_log_path() if enable_logging else None
    spawned = spawn_detached_dreamer(log_file=log_path)

    if spawned:
        return {
            "success": True,
            "message": "Dream worker spawned successfully. Consolidation will run in background.",
            "status": "spawned",
            "log_file": str(log_path) if log_path else None,
        }
    else:
        return {
            "success": False,
            "message": "Failed to spawn dream worker. Check logs for details.",
            "status": "failed",
        }


@mcp.tool(name="exo_consolidate")
def consolidate(
    tag_filter: str | None = None,
    min_cluster_size: int = 3,
) -> dict[str, Any]:
    """Extract patterns from clusters of similar memories.

    This implements the "Abstraction" mechanism (Phase 2) that:
    1. Finds clusters of similar memories (by tag or similarity)
    2. Identifies common patterns/rules across the cluster
    3. Creates Pattern nodes and links instances

    Patterns are abstract rules/insights extracted from concrete memories.
    Example patterns:
    - "Always use connection pooling for database connections"
    - "Check environment variables before deployment"

    Use this to:
    - Discover common patterns in your knowledge base
    - Create hierarchical knowledge (concrete → abstract)
    - Find generalizable insights from specific experiences

    Args:
        tag_filter: Optional tag to focus pattern extraction (e.g., "bugfix", "performance").
                    If not provided, focuses on frequently accessed memories.
        min_cluster_size: Minimum memories to form a pattern (default: 3).

    Returns:
        Summary of patterns found/created.
    """
    container = get_container()

    result = container.memory_service.consolidate_patterns(
        tag_filter=tag_filter,
        min_cluster_size=min_cluster_size,
        similarity_threshold=0.7,
    )

    return {
        "success": True,
        "patterns_found": result["patterns_found"],
        "patterns_created": result["patterns_created"],
        "memories_linked": result["memories_linked"],
        "details": result["details"],
        "message": (
            f"Consolidation complete: {result['patterns_created']} new patterns created, "
            f"{result['patterns_found']} existing patterns strengthened, "
            f"{result['memories_linked']} memories linked."
        ),
    }
