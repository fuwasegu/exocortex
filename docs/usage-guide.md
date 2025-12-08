# Exocortex Usage Guide 🧠

A practical guide to using Exocortex, the "second brain" for AI agents.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Tool Reference](#tool-reference)
3. [Practical Workflows](#practical-workflows)
4. [Prompting Tips](#prompting-tips)

---

## Basic Usage

### Storing Memories

Save insights, decisions, and lessons learned during development.

```
💬 User: "Remember this design decision"

🤖 AI: Uses exo_store_memory
```

**Example Prompts:**
- "Remember this implementation pattern"
- "Save this failure and how I fixed it"
- "Store the reasoning behind this design decision"

### Recalling Memories

Search for relevant past knowledge.

```
💬 User: "How did we implement authorization before?"

🤖 AI: Uses exo_recall_memories → Presents relevant memories
```

**Example Prompts:**
- "Recall Laravel authorization patterns"
- "Have I fixed a similar bug before?"
- "What should I watch out for with DDD design?"

---

## Tool Reference

### 📝 Store Memory (`exo_store_memory`)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `content` | Memory content (Markdown supported) | Design decision details |
| `context_name` | Project/situation name | `"my-project"`, `"exocortex"` |
| `tags` | Related keywords | `["laravel", "ddd", "architecture"]` |
| `memory_type` | Type of memory | `insight`, `success`, `failure`, `decision`, `note` |

**Effective Usage:**

```markdown
# ✅ Good: Structured content
## Problem
What happened with X

## Solution
Applied Y pattern

## Rationale
- Reason 1
- Reason 2

# ❌ Bad: Vague content
It worked somehow
```

---

### 🔍 Recall Memories (`exo_recall_memories`)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `query` | Search query (natural language) | `"authorization patterns"` |
| `limit` | Maximum results | `5` (default) |
| `context_filter` | Filter by project | `"my-project"` |
| `tag_filter` | Filter by tags | `["laravel", "ddd"]` |
| `type_filter` | Filter by type | `"decision"` |

**Search Tips:**

```
# ✅ Good: Specific queries
"Laravel authorization patterns without Policy"
"UUID Value Object implementation gotchas"

# ❌ Bad: Vague queries
"authorization"
"design"
```

---

### 🔗 Link Memories (`exo_link_memories`)

Connect memories to build a knowledge graph.

| Relation | Meaning | Use Case |
|----------|---------|----------|
| `related` | General relation | Different aspects of same topic |
| `extends` | Extends/builds upon | Application of base pattern |
| `depends_on` | Dependency | Requires prerequisite knowledge |
| `supersedes` | Replaces | Updated knowledge |
| `contradicts` | Conflicts | Context-dependent choices |

**Example Prompts:**
- "Link the authorization-related memories"
- "This extends the previous pattern, link them"

---

### 🌐 Explore Related (`exo_explore_related`)

Explore related knowledge starting from a memory.

**Exploration Scope:**
1. **Direct Links**: Connected via `exo_link_memories`
2. **Tag Siblings**: Memories sharing same tags
3. **Context Siblings**: Memories from same project

---

### 😴 Sleep / Consolidate (`exo_sleep`)

Background knowledge base maintenance.

**Tasks Performed:**
1. **Deduplication**: Detect memories with 95%+ similarity
2. **Orphan Rescue**: Link isolated memories
3. **Pattern Mining**: Conceptualize frequently accessed topics

**Example Prompts:**
- "Organize my memories"
- "Sleep" (literally!)
- "Maintain the knowledge base"

> ⚠️ **Note**: May be unstable in proxy mode (`--mode proxy`)

---

### 🔬 Consolidate Patterns (`exo_consolidate`)

Extract common patterns from similar memories.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `tag_filter` | Target tag | `"bugfix"`, `"performance"` |
| `min_cluster_size` | Minimum cluster size | `3` (default) |

**Example Prompts:**
- "Extract patterns from bugfix memories"
- "Summarize Laravel insights"

---

### 📊 Get Stats (`exo_get_stats`)

Display knowledge base overview.

```json
{
  "total_memories": 30,
  "memories_by_type": {
    "insight": 22,
    "decision": 7,
    "success": 1
  },
  "top_tags": ["laravel", "architecture", "ddd"]
}
```

---

### 🏥 Analyze Knowledge (`exo_analyze_knowledge`)

Diagnose knowledge base health.

**Detected Issues:**
- Orphan memories (no tags)
- Unlinked memories
- Stale memories (90+ days without update)

---

## Practical Workflows

### 🔄 Development Session Flow

```
1. Session Start
   └─ exo_recall_memories: Review relevant past knowledge

2. During Development
   └─ exo_store_memory: Save decisions and discoveries

3. Session End
   └─ exo_sleep: Organize knowledge base
```

### 📚 Knowledge Structuring Flow

```
1. Accumulate individual memories
   └─ exo_store_memory × N times

2. Link related memories
   └─ exo_link_memories to build knowledge graph

3. Extract patterns
   └─ exo_consolidate to abstract

4. Regular maintenance
   └─ exo_sleep for deduplication & orphan rescue
```

### 🐛 Debug Assistance Flow

```
💬 "Have I seen this error before?"

1. exo_recall_memories to search similar errors
2. If found → Apply past solution
3. If not found → Save with exo_store_memory after solving
```

### 🏗️ Design Review Flow

```
💬 "What do you think of this design?"

1. exo_recall_memories for related design patterns
2. exo_explore_related for surrounding knowledge
3. Compare with past decisions and advise
```

---

## Prompting Tips

### When Storing Memories

| Situation | Example Prompt |
|-----------|----------------|
| Design decision | "Remember this decision and why" |
| Bug fix | "Save this bug and solution" |
| Learning | "Store what I learned today" |
| Failure | "Record this failure for future reference" |

### When Searching Memories

| Situation | Example Prompt |
|-----------|----------------|
| Implementation | "Recall the pattern for X" |
| Past decisions | "Why did we choose Y?" |
| Troubleshooting | "Seen this error before?" |
| Best practices | "Best practices for Z?" |

### When Organizing

| Situation | Example Prompt |
|-----------|----------------|
| Regular maintenance | "Organize the knowledge base" |
| Pattern discovery | "Find patterns in X-related memories" |
| Health check | "How's the knowledge base looking?" |
| Exploration | "Find related knowledge" |

---

## Tips & Tricks

### 🏷️ Effective Tagging

```
# ✅ Good: Hierarchical & specific
tags: ["laravel", "eloquent", "query-optimization", "n+1"]

# ❌ Bad: Vague & too broad
tags: ["code", "fix"]
```

### 📝 Structured Content

```markdown
# Title

## Background / Problem
What was happening

## Solution
How it was solved

## Rationale
Why this approach was chosen

## Caveats
Things to watch out for
```

### 🔗 Using Links Effectively

- **New insight** → Link to existing related memory with `extends`
- **Conflicting info** → Link with `contradicts`, keep both
- **Updated info** → Create new memory, link with `supersedes`

---

Happy Hacking with your Second Brain! 🧠✨

