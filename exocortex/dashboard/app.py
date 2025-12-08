"""Dashboard Starlette application."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ..config import get_config
from ..container import get_container

logger = logging.getLogger(__name__)

# Path to static files
STATIC_DIR = Path(__file__).parent / "static"


async def index(request: Request) -> HTMLResponse:
    """Serve the main dashboard page."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


async def api_stats(request: Request) -> JSONResponse:
    """Get memory statistics."""
    try:
        container = get_container()
        repo = container.repository

        # Get stats using the existing get_stats method
        stats = repo.get_stats()

        # Get context names using repository's internal method
        result = repo._execute_read("MATCH (c:Context) RETURN c.name ORDER BY c.name")
        contexts = []
        while result.has_next():
            contexts.append(result.get_next()[0])

        # Get tag names
        result = repo._execute_read("MATCH (t:Tag) RETURN t.name ORDER BY t.name")
        tags = []
        while result.has_next():
            tags.append(result.get_next()[0])

        # Get orphan count
        orphans = repo.get_orphan_memories()

        return JSONResponse({
            "success": True,
            "stats": {
                "total_memories": stats.total_memories,
                "by_type": stats.memories_by_type,
                "contexts_count": stats.total_contexts,
                "tags_count": stats.total_tags,
                "orphan_count": len(orphans),
                "contexts": contexts[:20],  # Limit to 20
                "tags": tags[:50],  # Limit to 50
            }
        })
    except Exception as e:
        logger.exception("Error getting stats")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_memories(request: Request) -> JSONResponse:
    """List memories with optional filtering."""
    try:
        container = get_container()
        repo = container.repository

        # Parse query params
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
        context_filter = request.query_params.get("context")
        type_filter = request.query_params.get("type")
        tag_filter = request.query_params.get("tag")

        tags = [tag_filter] if tag_filter else None

        # list_memories returns (memories, total_count, has_more)
        memories, total, _has_more = repo.list_memories(
            limit=limit,
            offset=offset,
            context_filter=context_filter,
            type_filter=type_filter,
            tag_filter=tags,
        )

        return JSONResponse({
            "success": True,
            "memories": [
                {
                    "id": m.id,
                    "summary": m.summary[:200] if m.summary else m.content[:200],
                    "context_name": m.context,  # MemoryWithContext uses 'context' not 'context_name'
                    "memory_type": m.memory_type.value if m.memory_type else None,
                    "tags": m.tags,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "access_count": m.access_count,
                }
                for m in memories
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.exception("Error listing memories")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_memory_detail(request: Request) -> JSONResponse:
    """Get a single memory by ID."""
    try:
        memory_id = request.path_params["memory_id"]
        container = get_container()
        repo = container.repository

        memory = repo.get_by_id(memory_id)
        if not memory:
            return JSONResponse(
                {"success": False, "error": "Memory not found"},
                status_code=404
            )

        # Get links
        links = repo.get_links(memory_id)

        return JSONResponse({
            "success": True,
            "memory": {
                "id": memory.id,
                "content": memory.content,
                "summary": memory.summary,
                "context_name": memory.context,
                "memory_type": memory.memory_type.value if memory.memory_type else None,
                "tags": memory.tags,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
                "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
                "access_count": memory.access_count,
                "last_accessed_at": memory.last_accessed_at.isoformat() if memory.last_accessed_at else None,
            },
            "links": [
                {
                    "target_id": link.target_id,
                    "target_summary": link.target_summary or "",
                    "relation_type": link.relation_type.value if link.relation_type else None,
                    "reason": link.reason,
                }
                for link in links
            ]
        })
    except Exception as e:
        logger.exception("Error getting memory detail")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def api_health(request: Request) -> JSONResponse:
    """Get knowledge base health analysis."""
    try:
        container = get_container()
        repo = container.repository

        stats = repo.get_stats()
        total = stats.total_memories
        orphans = repo.get_orphan_memories()

        # Calculate health score
        orphan_ratio = len(orphans) / total if total > 0 else 0
        health_score = max(0, 100 - (orphan_ratio * 100))

        issues = []
        suggestions = []

        if len(orphans) > 0:
            issues.append(f"{len(orphans)} orphan memories without links")
            suggestions.append("Run exo_sleep to consolidate orphan memories")

        if total < 10:
            suggestions.append("Keep storing memories to build your knowledge base!")

        if not issues:
            suggestions.insert(0, "Your knowledge base looks healthy!")

        return JSONResponse({
            "success": True,
            "health": {
                "score": round(health_score, 1),
                "total_memories": total,
                "orphan_count": len(orphans),
                "issues": issues,
                "suggestions": suggestions,
            }
        })
    except Exception as e:
        logger.exception("Error analyzing health")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def stream_dream_log(request: Request) -> StreamingResponse:
    """Stream dream.log contents via SSE."""
    config = get_config()
    log_file = config.data_dir / "logs" / "dream.log"

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send initial content if file exists
        if log_file.exists():
            content = log_file.read_text()
            lines = content.strip().split("\n") if content.strip() else []
            # Send last 100 lines
            for line in lines[-100:]:
                if line.strip():
                    yield f"data: {json.dumps({'type': 'log', 'content': line})}\n\n"

        # Watch for new content
        last_size = log_file.stat().st_size if log_file.exists() else 0

        while True:
            await asyncio.sleep(1)

            # Check if client disconnected
            if await request.is_disconnected():
                break

            if not log_file.exists():
                continue

            current_size = log_file.stat().st_size
            if current_size > last_size:
                # Read new content
                with open(log_file) as f:
                    f.seek(last_size)
                    new_content = f.read()

                for line in new_content.strip().split("\n"):
                    if line.strip():
                        yield f"data: {json.dumps({'type': 'log', 'content': line})}\n\n"

                last_size = current_size
            elif current_size < last_size:
                # File was truncated/rotated
                last_size = 0

            # Send heartbeat
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


async def api_graph(request: Request) -> JSONResponse:
    """Get graph data for visualization."""
    try:
        container = get_container()
        repo = container.repository

        # Get all memories (limited)
        memories, _total, _has_more = repo.list_memories(limit=100, offset=0)

        nodes = []
        edges = []
        seen_edges = set()

        for memory in memories:
            nodes.append({
                "id": memory.id,
                "label": (memory.summary or memory.content)[:50],
                "type": memory.memory_type.value if memory.memory_type else "note",
                "context": memory.context,
            })

            # Get links for this memory
            memory_links = repo.get_links(memory.id)
            for link in memory_links:
                edge_key = (memory.id, link.target_id)
                if edge_key not in seen_edges:
                    edges.append({
                        "source": memory.id,
                        "target": link.target_id,
                        "type": link.relation_type.value if link.relation_type else "related",
                    })
                    seen_edges.add(edge_key)

        return JSONResponse({
            "success": True,
            "graph": {
                "nodes": nodes,
                "edges": edges,
            }
        })
    except Exception as e:
        logger.exception("Error getting graph data")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


def create_dashboard_app() -> Starlette:
    """Create the dashboard Starlette application."""
    routes = [
        Route("/", index),
        Route("/api/stats", api_stats),
        Route("/api/memories", api_memories),
        Route("/api/memories/{memory_id}", api_memory_detail),
        Route("/api/health", api_health),
        Route("/api/graph", api_graph),
        Route("/api/logs/stream", stream_dream_log),
    ]

    # Add static files if directory exists
    if STATIC_DIR.exists():
        routes.append(
            Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        )

    app = Starlette(routes=routes)
    return app

