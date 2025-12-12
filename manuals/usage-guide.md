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
| `context_name` | Project/situation name | `"my-webapp"`, `"api-server"` |
| `tags` | Related keywords | `["laravel", "ddd", "architecture"]` |
| `memory_type` | Type of memory | `insight`, `success`, `failure`, `decision`, `note` |
| `is_painful` | 🔥 Painful memory flag (optional) | `true` to prioritize as a debugging nightmare |
| `time_cost_hours` | Time spent (optional) | `3.0` to record 3 hours |

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

**🔥 Storing Painful Memories:**

```markdown
# ✅ Good: Explicitly mark debugging struggles
💬 "This bug took 3 hours to fix, remember it"

🤖 AI: exo_store_memory(
    content="...",
    is_painful=True,
    time_cost_hours=3.0
)
```

Content with "nightmare", "stuck", or "frustrated" is auto-detected, but explicitly setting `is_painful=True` ensures priority.

---

### 🔍 Recall Memories (`exo_recall_memories`)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `query` | Search query (natural language) | `"authorization patterns"` |
| `limit` | Maximum results | `5` (default) |
| `context_filter` | Filter by project | `"my-webapp"` |
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
| `evolved_from` | Evolved from | Decision evolved over time |
| `rejected_because` | Rejected due to | Approach rejected for a reason |
| `caused_by` | Caused by | Result caused by a prior event |

**Example Prompts:**
- "Link the authorization-related memories"
- "This extends the previous pattern, link them"
- "This decision evolved from the previous one, link with evolved_from"

---

### 🕰️ Trace Lineage (`exo_trace_lineage`)

Trace the **evolution and history** of a memory. Understand how decisions evolved over time.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `memory_id` | Starting memory ID | Memory to trace from |
| `direction` | `"backward"` (ancestors) or `"forward"` (descendants) | `"backward"` |
| `relation_types` | Relations to follow | `["evolved_from", "caused_by"]` |
| `max_depth` | Max traversal depth | `10` (default) |

**Example Prompts:**
- "Why did we make this decision? Trace its history"
- "What led to this bug? Show the lineage"
- "How did this architecture evolve?"

**Use Cases:**
- **Architecture archaeology**: Understand why things are the way they are
- **Root cause analysis**: Trace problems back to their origin
- **Decision audit**: Review the evolution of key decisions

---

### 🤔 Curiosity Scan (`exo_curiosity_scan`)

Scan your knowledge base for contradictions, suggested links, outdated info, and generate questions.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `context_filter` | Filter by project | `"my-webapp"` |
| `tag_filter` | Filter by tags | `["architecture"]` |
| `max_findings` | Max findings per category | `10` (default) |

**What it detects:**
- 🔴 **Contradictions**: Success vs Failure on same topic
- 🔗 **Suggested Links**: Unlinked memories that should be connected
- 📅 **Outdated Info**: Old knowledge not marked as superseded
- ❓ **Questions**: Human-like questions about your knowledge

**Suggested Link Detection Strategies:**

| Strategy | Description |
|----------|-------------|
| **Tag Sharing** | Memories sharing 2+ tags (high confidence) |
| **Context Sharing** | Same project + same type (medium confidence) |
| **Semantic Similarity** | High vector similarity >70% (high confidence) |

**Example Prompts:**
- "Are there any contradictions in my knowledge?"
- "Find unlinked memories that should be connected"
- "Question my assumptions about the database design"
- "Scan for inconsistencies in my project"

**Automated Link Creation:**

The response includes `next_actions` with suggested `exo_link_memories` calls:

```json
{
  "suggested_links": [...],
  "next_actions": [
    {
      "action": "create_link",
      "priority": "medium",
      "details": {
        "call": "exo_link_memories",
        "args": { "source_id": "...", "target_id": "...", "relation_type": "related" }
      }
    }
  ]
}
```

**🤖 Optional: BERT-based Sentiment Analysis**

For higher accuracy, install `exocortex[sentiment]` to enable BERT model:

```bash
pip install exocortex[sentiment]
```

Without it, keyword-based detection is used (works well for most cases).

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

### 🤔 Knowledge Quality Flow

```
💬 "Are there any issues with my knowledge base?"

1. exo_curiosity_scan to detect contradictions, suggested links, and outdated info
2. Review the generated questions
3. Execute next_actions to create suggested links
4. Link contradicting memories with evolved_from or supersedes
5. Mark outdated memories as superseded
```

### 🔗 Graph Enrichment Flow

```
💬 "Find unlinked memories and connect them"

1. exo_curiosity_scan → Returns suggested_links
2. AI executes next_actions (exo_link_memories calls)
3. Knowledge graph becomes richer and more interconnected
```

**Example:**
```
Contradiction detected:
├─ "Caching works great" (success)
└─ "Caching failed badly" (failure)
    ↳ Link with evolved_from if it was a learning journey
    ↳ Link with supersedes if one replaces the other
```

### 🕰️ Decision Archaeology Flow

```
💬 "Why did we choose this architecture?"

1. exo_trace_lineage(direction="backward") to find ancestors
2. Follow the evolved_from and caused_by chains
3. Understand the full history of the decision
```

**Example:**
```
Current: Microservices Architecture
    │
    ▼ trace_lineage(backward)
    │
    ├─ [depth 1] "Migrated from monolith" (evolved_from)
    │
    └─ [depth 2] "Database scaling issues" (caused_by)
           ↳ Root cause identified!
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
| 🔥 Debugging struggle | "This took 3 hours to debug, save it as a painful memory" |
| 🔥 Hard-won solution | "This was a nightmare, remember it so we don't repeat it" |

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
- **Decision evolution** → Link with `evolved_from` to track how decisions changed
- **Root cause** → Link with `caused_by` to connect effects to causes
- **Rejected approach** → Link with `rejected_because` to remember why something was abandoned

### 🔥 Frustration Indexing (Somatic Marker Hypothesis)

**"Painful memories are prioritized in decision-making"** — backed by neuroscience.

- **Debugging struggles** → Save with `is_painful=True` → Boosted in search
- **Time-consuming problems** → Record `time_cost_hours` → Affects frustration score
- Content with "nightmare", "stuck", "frustrated", "impossible" is auto-detected

```
# More 🔥 = Higher priority
🔥🔥🔥 extreme (0.8-1.0): Never want to repeat
🔥🔥   high    (0.6-0.8): Really struggled
🔥     medium  (0.4-0.6): Moderately frustrating
😓     low     (0.2-0.4): Slightly tricky
```

**Example Prompts:**
```
💬 "Have I been stuck on a similar bug before?"
    → Painful memories surface first 🔥

💬 "This was hell to debug... remember it"
    → Auto-detected as high frustration
```

---

Happy Hacking with your Second Brain! 🧠✨

