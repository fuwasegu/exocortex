"""MCP Server definition for Exocortex."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .config import get_config
from .db import get_db
from .models import MemoryType

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    "Exocortex",
    instructions=(
        "Exocortex is your external brain - a local MCP server that stores "
        "and retrieves development insights, technical decisions, and "
        "troubleshooting knowledge. Use store_memory to save new insights "
        "and recall_memories to find relevant past experiences."
    ),
)


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

    Args:
        content: The content to store (supports Markdown).
        context_name: The project or situation name where this memory originated.
        tags: List of related keywords/tags for categorization.
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

        return {
            "success": result.success,
            "memory_id": result.memory_id,
            "summary": result.summary,
        }

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


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp
