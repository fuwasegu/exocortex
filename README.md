# Exocortex 🧠

> "Extend your mind." - Your External Brain

**[日本語版はこちら (Japanese)](./README.ja.md)**

---

**Exocortex** is a local MCP (Model Context Protocol) server that acts as a developer's "second brain."

It persists development insights, technical decisions, and troubleshooting records, allowing AI assistants (like Cursor) to retrieve contextually relevant memories when needed.

## Features

- 🔒 **Fully Local**: All data and AI processing stays on your machine. Privacy guaranteed.
- 🔍 **Semantic Search**: Find memories by meaning, not just keywords.
- 🕸️ **Graph Structure**: Maintains relationships between projects, tags, and memories.
- ⚡ **Lightweight & Fast**: Uses embedded KùzuDB and lightweight fastembed models.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/exocortex.git
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

## MCP Tools

| Tool | Description |
|------|-------------|
| `ping` | Health check to verify server is running |
| `store_memory` | Store a new memory |
| `recall_memories` | Recall relevant memories via semantic search |
| `list_memories` | List stored memories |
| `get_memory` | Get a specific memory by ID |
| `delete_memory` | Delete a memory |
| `get_stats` | Get statistics about stored memories |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXOCORTEX_DATA_DIR` | `./data` | Database storage directory |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `EXOCORTEX_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model to use |

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with debug logging
EXOCORTEX_LOG_LEVEL=DEBUG uv run exocortex
```

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

## License

MIT License
