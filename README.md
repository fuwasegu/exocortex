# Exocortex 🧠

> "Extend your mind." - Your External Brain

**[日本語版はこちら (Japanese)](./README.ja.md)**

---

**Exocortex** is a local MCP (Model Context Protocol) server that acts as a developer's "second brain."

It persists development insights, technical decisions, and troubleshooting records, allowing AI assistants (like Cursor) to retrieve contextually relevant memories when needed.

## Why Exocortex?

### 🌐 Cross-Project Knowledge Sharing

Unlike tools that store data per-repository (e.g., `.serena/` in each project), **Exocortex uses a single, centralized knowledge store**.

```
Traditional approach (per-repository):
project-A/.serena/    ← isolated knowledge
project-B/.serena/    ← isolated knowledge
project-C/.serena/    ← isolated knowledge

Exocortex approach (centralized):
~/.exocortex/data/    ← shared knowledge across ALL projects
    ├── Insights from project-A
    ├── Insights from project-B
    └── Insights from project-C
        ↓
    Cross-project learning!
```

**Benefits:**
- 🔄 **Knowledge Transfer**: Lessons learned in one project are immediately available in others
- 🏷️ **Tag-based Discovery**: Find related memories across projects via shared tags
- 📈 **Cumulative Learning**: Your external brain grows smarter over time, not per project
- 🔍 **Pattern Recognition**: Discover common problems and solutions across your entire development history

## Features

- 🔒 **Fully Local**: All data and AI processing stays on your machine. Privacy guaranteed.
- 🔍 **Semantic Search**: Find memories by meaning, not just keywords.
- 🕸️ **Knowledge Graph**: Maintains relationships between projects, tags, and memories with explicit links.
- 🔗 **Memory Links**: Connect related memories to build a traversable knowledge network.
- ⚡ **Lightweight & Fast**: Uses embedded KùzuDB and lightweight fastembed models.
- 🧠 **Memory Dynamics**: Smart recall based on recency and frequency—frequently accessed memories surface higher.
- 🔥 **Frustration Indexing**: Prioritize "painful memories"—debugging nightmares get boosted in search results.
- 🖥️ **Web Dashboard**: Beautiful cyberpunk-style UI for browsing memories, monitoring health, and visualizing the knowledge graph.

## 📚 Usage Guide

**→ [See the full usage guide](./manuals/usage-guide.md)**

- Tool reference with use cases
- Practical workflows
- Prompting tips
- Tips & Tricks

## Installation

```bash
# Clone the repository
git clone https://github.com/fuwasegu/exocortex.git
cd exocortex

# Install dependencies with uv
uv sync
```

## Usage

### Starting the Server

```bash
uv run exocortex
```

### Cursor Configuration

Add the following to your `~/.cursor/mcp.json`:

#### Option 1: Direct from GitHub (Recommended)

Auto-updates when uvx cache expires. No manual `git pull` needed.

```json
{
  "mcpServers": {
    "exocortex": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/fuwasegu/exocortex", "exocortex"]
    }
  }
}
```

#### Option 2: Local Installation

For development or customization.

```json
{
  "mcpServers": {
    "exocortex": {
      "command": "uv",
      "args": ["--directory", "/path/to/exocortex", "run", "exocortex"]
    }
  }
}
```

> **Note:** Your data is stored in `~/.exocortex/` and is preserved regardless of which option you choose.

#### Option 3: Proxy Mode (Multiple Cursor Instances - Recommended)

**Use this method if you want to use Exocortex from multiple Cursor windows simultaneously.**

KùzuDB doesn't support concurrent writes from multiple processes. With the stdio approach where each Cursor instance spawns its own server process, lock conflicts occur. Proxy mode automatically starts a single SSE server in the background, and each Cursor instance connects via proxy.

```json
{
  "mcpServers": {
    "exocortex": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/fuwasegu/exocortex",
        "exocortex",
        "--mode", "proxy",
        "--ensure-server"
      ]
    }
  }
}
```

**How it works:**
1. First Cursor starts Exocortex → SSE server automatically starts in background
2. Subsequent Cursors connect to the existing SSE server
3. All Cursors share the same server → No lock conflicts!

> **Note:** No manual server startup required. The `--ensure-server` option automatically starts the server if it's not running.

#### Option 4: Manual Server Management (Advanced)

If you prefer to manage the server manually:

**Step 1: Start the server**

```bash
# Start the server in a terminal (can also run in background)
uv run --directory /path/to/exocortex exocortex --transport sse --port 8765
```

**Step 2: Configure Cursor**

```json
{
  "mcpServers": {
    "exocortex": {
      "url": "http://127.0.0.1:8765/mcp/sse"
    }
  }
}
```

> **Bonus:** With this setup, you can also access the web dashboard at `http://127.0.0.1:8765/`

> **Tip:** To auto-start the server on system boot, use `launchd` on macOS or `systemd` on Linux.

## MCP Tools

### Basic Tools

| Tool | Description |
|------|-------------|
| `exo_ping` | Health check to verify server is running |
| `exo_store_memory` | Store a new memory |
| `exo_recall_memories` | Recall relevant memories via semantic search |
| `exo_list_memories` | List stored memories with pagination |
| `exo_get_memory` | Get a specific memory by ID |
| `exo_delete_memory` | Delete a memory |
| `exo_get_stats` | Get statistics about stored memories |

### Advanced Tools

| Tool | Description |
|------|-------------|
| `exo_link_memories` | Create a link between two memories |
| `exo_unlink_memories` | Remove a link between memories |
| `exo_update_memory` | Update content, tags, or type of a memory |
| `exo_explore_related` | Discover related memories via graph traversal |
| `exo_get_memory_links` | Get all outgoing links from a memory |
| `exo_trace_lineage` | 🕰️ Trace the evolution/lineage of a memory (temporal reasoning) |
| `exo_analyze_knowledge` | Analyze knowledge base health and get improvement suggestions |
| `exo_sleep` | Trigger background consolidation (deduplication, orphan rescue) |
| `exo_consolidate` | Extract abstract patterns from memory clusters |

### 🤖 Knowledge Autonomy

Exocortex automatically improves your knowledge graph! When you store a memory, the system:

1. **Suggests Links**: Finds similar existing memories and suggests connections
2. **Detects Duplicates**: Warns if the new memory is too similar to an existing one
3. **Identifies Patterns**: Recognizes when a success might resolve a past failure

```json
// Example exo_store_memory response with suggestions
{
  "success": true,
  "memory_id": "...",
  "suggested_links": [
    {
      "target_id": "existing-memory-id",
      "similarity": 0.78,
      "suggested_relation": "extends",
      "reason": "High semantic similarity; may be an application of this insight"
    }
  ],
  "insights": [
    {
      "type": "potential_duplicate",
      "message": "This memory is very similar (94%) to an existing one.",
      "suggested_action": "Use exo_update_memory instead"
    }
  ]
}
```

### 🧠 Automatic Memory Consolidation

**Like human sleep consolidates memories, Exocortex prompts the AI to organize after storing.**

When `exo_store_memory` succeeds, the response includes `next_actions` that guide the AI to:

1. **Link high-similarity memories** (similarity ≥ 0.7)
2. **Handle duplicates and contradictions**
3. **Run periodic health checks** (every 10 memories)

```json
// Example response with next_actions
{
  "success": true,
  "memory_id": "abc123",
  "summary": "...",
  "consolidation_required": true,
  "consolidation_message": "🧠 Memory stored. 2 consolidation action(s) required.",
  "next_actions": [
    {
      "action": "link_memories",
      "priority": "high",
      "description": "Link to 2 related memories",
      "details": [
        {
          "call": "exo_link_memories",
          "args": {
            "source_id": "abc123",
            "target_id": "def456",
            "relation_type": "extends",
            "reason": "High semantic similarity"
          }
        }
      ]
    },
    {
      "action": "analyze_health",
      "priority": "low",
      "description": "Run knowledge base health check",
      "details": { "call": "exo_analyze_knowledge" }
    }
  ]
}
```

**Expected Flow:**
```
User: "Remember this insight"
    ↓
AI: exo_store_memory() → receives next_actions
    ↓
AI: exo_link_memories() for each high-priority action
    ↓
AI: "Stored and linked to 2 related memories."
```

> ⚠️ **Important Limitation**: Execution of `next_actions` is at the AI agent's discretion. While the server strongly instructs consolidation via `SERVER_INSTRUCTIONS` and `consolidation_required: true`, **execution is NOT 100% guaranteed**. This is an inherent limitation of the MCP protocol—servers can only suggest, not force actions. In practice, most modern AI assistants follow these instructions, but they may be skipped during complex conversations or when competing with other tasks.

### Relation Types for `exo_link_memories`

| Type | Description |
|------|-------------|
| `related` | Generally related memories |
| `supersedes` | This memory updates/replaces the target |
| `contradicts` | This memory contradicts the target |
| `extends` | This memory extends/elaborates the target |
| `depends_on` | This memory depends on the target |
| `evolved_from` | This memory evolved from the target (temporal reasoning) |
| `rejected_because` | This memory was rejected due to the target |
| `caused_by` | This memory was caused by the target |

### Temporal Reasoning with `exo_trace_lineage`

Trace the **lineage of decisions and knowledge** over time. Understand WHY something became the way it is.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `memory_id` | Starting memory ID | `"abc123"` |
| `direction` | `"backward"` (find ancestors) or `"forward"` (find descendants) | `"backward"` |
| `relation_types` | Relations to follow | `["evolved_from", "caused_by"]` |
| `max_depth` | Maximum traversal depth | `10` (default) |

**Example: Understanding Why a Decision Was Made**

```
Current Architecture Decision
    │
    ▼ trace_lineage(direction="backward")
    │
    ├─ [depth 1] Previous Design (evolved_from)
    │      "Switched from monolith to microservices"
    │
    └─ [depth 2] Original Problem (caused_by)
           "Scaling issues with single database"
```

**Usage:**
```
AI: exo_trace_lineage(memory_id="current-decision", direction="backward")
    ↓
Result: Shows the evolution chain of how the current decision came to be
```

**Use Cases:**
- 🔍 **Architecture archaeology**: "Why did we choose this approach?"
- 🐛 **Root cause analysis**: "What led to this bug?"
- 📚 **Knowledge evolution**: "How has our understanding changed?"

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXOCORTEX_DATA_DIR` | `~/.exocortex` | Database storage directory |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `EXOCORTEX_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model to use |
| `EXOCORTEX_TRANSPORT` | `stdio` | Transport mode (stdio/sse/streamable-http) |
| `EXOCORTEX_HOST` | `127.0.0.1` | Server bind address (for HTTP modes) |
| `EXOCORTEX_PORT` | `8765` | Server port number (for HTTP modes) |

## Architecture

### Stdio Mode (Default)

```
┌─────────────────┐     stdio      ┌─────────────────────────────┐
│  AI Assistant   │ ◄──────────► │       Exocortex MCP         │
│   (Cursor)      │    MCP        │                             │
└─────────────────┘               │  ┌─────────┐  ┌──────────┐  │
                                  │  │ Tools   │  │ Embedding│  │
                                  │  │ Handler │  │  Engine  │  │
                                  │  └────┬────┘  └────┬─────┘  │
                                  │       │            │        │
                                  │  ┌────▼────────────▼─────┐  │
                                  │  │       KùzuDB          │  │
                                  │  │  (Graph + Vector)     │  │
                                  │  └────────────────────────┘  │
                                  └─────────────────────────────┘
```

### HTTP/SSE Mode (Multiple Instances)

```
┌─────────────────┐                
│  Cursor #1      │──────┐         
└─────────────────┘      │         
                         │  HTTP   ┌─────────────────────────────┐
┌─────────────────┐      ├────────►│       Exocortex MCP         │
│  Cursor #2      │──────┤   SSE   │      (Standalone)           │
└─────────────────┘      │         │                             │
                         │         │  ┌─────────┐  ┌──────────┐  │
┌─────────────────┐      │         │  │ Tools   │  │ Embedding│  │
│  Cursor #3      │──────┘         │  │ Handler │  │  Engine  │  │
└─────────────────┘                │  └────┬────┘  └────┬─────┘  │
                                   │       │            │        │
                                   │  ┌────▼────────────▼─────┐  │
                                   │  │       KùzuDB          │  │
                                   │  │  (Graph + Vector)     │  │
                                   │  └────────────────────────┘  │
                                   └─────────────────────────────┘
```

### Knowledge Graph Structure

```
Memory ─── ORIGINATED_IN ──► Context (project)
Memory ─── TAGGED_WITH ────► Tag
Memory ─── RELATED_TO ─────► Memory (with relation type)
```

### Memory Dynamics

Exocortex implements a **Memory Dynamics** system inspired by human cognition. Memories have "lifespan" and "strength" that affect search results:

**Hybrid Scoring Formula:**

```
Score = (S_vec × w_vec) + (S_recency × w_recency) + (S_freq × w_freq) + (S_frustration × w_frustration)
```

| Component | Description | Default Weight |
|-----------|-------------|----------------|
| `S_vec` | Vector similarity (semantic relevance) | 0.50 |
| `S_recency` | Recency score (exponential decay: e^(-λ×Δt)) | 0.20 |
| `S_freq` | Frequency score (log scale: log(1 + count)) | 0.15 |
| `S_frustration` | Frustration score (painful memory boost) | 0.15 |

**How it works:**
- Every time a memory is recalled, its `last_accessed_at` and `access_count` are updated
- Frequently accessed memories gain higher `S_freq` scores
- Recently accessed memories gain higher `S_recency` scores
- **Painful memories** (debugging nightmares) get higher `S_frustration` scores for priority
- Old, unused memories naturally decay but remain searchable

This creates an intelligent recall system where:
- 📈 Important memories (frequently used) stay prominent
- ⏰ Recent context is prioritized
- 🔥 **Painful memories are never forgotten**—to avoid repeating mistakes
- 🗃️ Old memories gracefully fade but don't disappear

### Frustration Indexing (Somatic Marker Hypothesis)

Based on the neuroscience insight that **"painful memories are prioritized in decision-making"**, Exocortex automatically boosts the importance of debugging struggles and hard-won solutions.

**Usage:**

```python
# Explicitly mark as a painful memory
exo_store_memory(
    content="Spent 3 hours debugging KùzuDB lock issues. Root cause was...",
    context_name="exocortex",
    tags=["bug", "kuzu"],
    is_painful=True,          # ← Important!
    time_cost_hours=3.0       # ← Record time spent
)
```

**Auto-detection:**
Even without `is_painful`, frustration level is auto-detected from content:

- 😓 **Low** (0.2-0.4): "tricky", "weird", "workaround"
- 🔥 **Medium** (0.4-0.6): "finally", "bug", "hours"
- 🔥🔥 **High** (0.6-0.8): "stuck", "frustrated"
- 🔥🔥🔥 **Extreme** (0.8-1.0): "nightmare", "impossible", "hell"

**Search results:**
```json
{
  "memories": [
    {
      "id": "...",
      "summary": "KùzuDB lock issue resolution",
      "frustration_score": 0.85,
      "pain_indicator": "🔥🔥🔥",   // ← Visual emphasis
      "time_cost_hours": 3.0
    }
  ]
}
```

### Sleep/Dream Mechanism

Like human sleep consolidates memories, Exocortex has a **background consolidation process** that organizes your knowledge graph:

```
┌─────────────────────────────────────────────────────────────┐
│                    exo_sleep() called                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Dream Worker (Detached Process)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Deduplication                                      │   │
│  │    - Find memories with similarity >= 95%             │   │
│  │    - Link newer → older with 'supersedes' relation    │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 2. Orphan Rescue                                      │   │
│  │    - Find memories with no tags and no links          │   │
│  │    - Link to most similar memory with 'related'       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 3. Pattern Mining (Phase 2)                           │   │
│  │    - Extract common patterns from memory clusters     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Usage:**
```
AI: "I've completed the task. Let me consolidate the knowledge base."
    ↓
AI: exo_sleep() → Worker spawns in background
    ↓
AI: "Consolidation process started. Your knowledge graph will be optimized."
```

**Key Features:**
- 🔄 **Non-blocking**: Returns immediately, consolidation runs in background
- 🔐 **Safe**: Uses file locking to avoid conflicts with active sessions
- 📊 **Logs**: Enable logging with `enable_logging=True` to track progress

> ⚠️ **Warning for Proxy Mode**: When using proxy mode (`--mode proxy`), `exo_sleep` is **NOT recommended**. In proxy mode, the SSE server maintains a constant connection to KùzuDB. The Dream Worker spawned in the background cannot access the database and will timeout or cause conflicts.
>
> **Workarounds:**
> - Don't use `exo_sleep` in proxy mode
> - Use it in stdio mode before ending a session
> - Manually stop the SSE server before running

### Pattern Abstraction (Concept Formation)

Exocortex can extract **abstract patterns** from concrete memories, creating a hierarchical knowledge structure:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Pattern Layer                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ "Always use connection pooling for database connections"   │  │
│  │ Confidence: 0.85 | Instances: 5                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                    ▲ INSTANCE_OF    ▲ INSTANCE_OF
       ┌────────────┴────────────────┴────────────┐
┌──────┴──────┐  ┌───────────┐  ┌───────────┐  ┌──┴────────┐
│ Memory #1   │  │ Memory #2 │  │ Memory #3 │  │ Memory #4 │
│ PostgreSQL  │  │ MySQL     │  │ Redis     │  │ MongoDB   │
│ pooling fix │  │ pool size │  │ conn reuse│  │ pool leak │
└─────────────┘  └───────────┘  └───────────┘  └───────────┘
                     Memory Layer (Concrete)
```

**Usage:**
```
AI: exo_consolidate(tag_filter="database") → Extracts patterns from database-related memories
    ↓
Result: "Created 2 patterns from 8 memories"
```

**Benefits:**
- 🎯 **Generalization**: Discover rules that apply across specific cases
- 🔍 **Meta-learning**: Find what works (and what doesn't) across projects
- 📈 **Confidence Building**: Patterns get stronger as more instances are linked

## Web Dashboard

Exocortex includes a beautiful web dashboard for visualizing and managing your knowledge base.

### Accessing the Dashboard

#### 🚀 If You're Using Proxy Mode (Recommended)

**No terminal commands needed!** When using proxy mode (`--mode proxy --ensure-server`) with Cursor, the SSE server is automatically running in the background.

**Just open this in your browser:**

```
http://127.0.0.1:8765/
```

```
Cursor starts
    ↓
Proxy mode → SSE server auto-starts (port 8765)
    ↓
├─ MCP: http://127.0.0.1:8765/mcp/sse ← Used by Cursor
└─ Dashboard: http://127.0.0.1:8765/ ← Just open in browser!
```

#### Starting the Server Manually

If you want to view the dashboard without using Cursor:

```bash
# Start SSE server (includes dashboard)
uv run exocortex --transport sse --port 8765
```

**URLs:**
- **Dashboard**: `http://127.0.0.1:8765/`
- **MCP SSE**: `http://127.0.0.1:8765/mcp/sse`

### Dashboard Features

| Tab | Description |
|-----|-------------|
| **Overview** | Statistics, contexts, tags, and knowledge base health score |
| **Memories** | Browse, filter, and search memories with pagination |
| **Dream Log** | Real-time streaming log of background consolidation processes |
| **Graph** | Visual knowledge graph showing memory connections |

### Screenshots

**Overview Tab**
- Total memories count by type (Insights, Successes, Failures, Decisions, Notes)
- Context and tag clouds for quick navigation
- Health score with improvement suggestions

**Memories Tab**
- Filter by type (Insight/Success/Failure/Decision/Note)
- Filter by context (project)
- Click any memory to see full details and links

**Graph Tab**
- Interactive node visualization
- Color-coded by memory type:
  - 🔵 Cyan: Insights
  - 🟠 Orange: Decisions
  - 🟢 Green: Successes
  - 🔴 Red: Failures
- Lines show `RELATED_TO` connections between memories

### Standalone Dashboard Mode

You can also run the dashboard separately on a different port:

```bash
uv run exocortex --mode dashboard --dashboard-port 8766
```

> **Note:** In standalone mode, the dashboard connects to the same database but doesn't include the MCP server.

## Documentation

- [Design Document](./docs/design_doc.md) - System design and specifications
- [Graph Architecture](./docs/graph_architecture.md) - How the knowledge graph works

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with debug logging
EXOCORTEX_LOG_LEVEL=DEBUG uv run exocortex
```

## License

MIT License
