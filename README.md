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
| `exo_analyze_knowledge` | Analyze knowledge base health and get improvement suggestions |

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

### Relation Types for `exo_link_memories`

| Type | Description |
|------|-------------|
| `related` | Generally related memories |
| `supersedes` | This memory updates/replaces the target |
| `contradicts` | This memory contradicts the target |
| `extends` | This memory extends/elaborates the target |
| `depends_on` | This memory depends on the target |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXOCORTEX_DATA_DIR` | `./data` | Database storage directory |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `EXOCORTEX_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model to use |

## Architecture

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

### Knowledge Graph Structure

```
Memory ─── ORIGINATED_IN ──► Context (project)
Memory ─── TAGGED_WITH ────► Tag
Memory ─── RELATED_TO ─────► Memory (with relation type)
```

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
