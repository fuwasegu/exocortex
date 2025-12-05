# Exocortex グラフアーキテクチャ解説

このドキュメントでは、Exocortexの知識グラフがどのように構築・成長していくかを解説します。

## 1. グラフ構造の概要

Exocortexは**KùzuDB**を使用して、記憶を**プロパティグラフ**として保存します。

### ノード（Nodes）

| ノード | 説明 | 主キー |
|--------|------|--------|
| **Memory** | 記憶の本体（コンテンツ + ベクトル埋め込み） | `id` (UUID) |
| **Context** | 記憶が形成された状況・プロジェクト | `name` |
| **Tag** | 関連する技術要素・概念 | `name` |

### リレーション（Edges）

| リレーション | 方向 | プロパティ | 説明 |
|-------------|------|-----------|------|
| `ORIGINATED_IN` | Memory → Context | - | 記憶がどのプロジェクトで生まれたか |
| `TAGGED_WITH` | Memory → Tag | - | 記憶にどのタグが付いているか |
| `RELATED_TO` | Memory → Memory | relation_type, reason, created_at | **記憶同士の明示的な関連付け** |

### グラフ構造の図

```
                        ┌─────────────────┐
                        │    Context      │
                        │ (プロジェクト)   │
                        └────────▲────────┘
                                 │
                          ORIGINATED_IN
                                 │
┌──────────┐          ┌──────────┴──────────┐          ┌──────────┐
│   Tag    │◄─────────│      Memory         │─────────►│   Tag    │
│ (技術A)  │ TAGGED   │   (記憶の本体)       │ TAGGED   │ (技術B)  │
└──────────┘  WITH    │                     │  WITH    └──────────┘
                      │ • id: UUID          │
                      │ • content: 本文     │
                      │ • summary: 要約     │
                      │ • embedding: ベクトル│
                      │ • memory_type: 種類 │
                      │ • created_at: 作成日│
                      │ • updated_at: 更新日│
                      └──────────┬──────────┘
                                 │
                            RELATED_TO
                         (relation_type,
                          reason)
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │   別の Memory       │
                      └─────────────────────┘
```

---

## 2. Memory間リレーション（RELATED_TO）

### 2.1 リレーションタイプ

| タイプ | 説明 | 使用例 |
|--------|------|--------|
| `related` | 一般的な関連 | 「同じトピックについての別の視点」 |
| `supersedes` | 更新/置換 | 「新しい解決策が古い方法を置き換える」 |
| `contradicts` | 矛盾 | 「この知見は以前の理解と矛盾する」 |
| `extends` | 拡張/詳細化 | 「原則の具体的な適用例」 |
| `depends_on` | 依存 | 「この解決策はあの知識を前提とする」 |

### 2.2 link_memories の処理フロー

```
┌─────────────────────────────────────────────────────────────┐
│                    link_memories 実行                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ ソースとターゲットのMemoryが存在するか確認              │
│                                                             │
│  2️⃣ RELATED_TO リレーションを作成                          │
│     CREATE (source)-[:RELATED_TO {                         │
│         relation_type: $type,                              │
│         reason: $reason,                                   │
│         created_at: $now                                   │
│     }]->(target)                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 リンクの活用例

```
【原則を記録】
Memory-1: "Principle: Always use connection pooling"
          (type: insight)

【具体的な適用を記録してリンク】
Memory-2: "Applied connection pooling to PostgreSQL"
          (type: success)
          
link_memories(
    source_id=Memory-2,
    target_id=Memory-1,
    relation_type="extends",
    reason="PostgreSQL specific implementation"
)

【結果のグラフ】
Memory-1 (原則)
    ▲
    │ RELATED_TO (extends)
    │
Memory-2 (適用例)
```

---

## 3. グラフ構築メカニズム

### 3.1 store_memory の処理フロー

`store_memory` が呼ばれると、以下の順序でグラフが構築されます：

```
┌─────────────────────────────────────────────────────────────┐
│                    store_memory 実行                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ コンテンツをベクトル化                                   │
│     content → embedding (384次元ベクトル)                    │
│                                                             │
│  2️⃣ Memory ノードを CREATE                                  │
│     新しいUUIDを生成してノードを作成                          │
│                                                             │
│  3️⃣ Context ノードを MERGE                                  │
│     • 存在しない場合 → 新規作成                              │
│     • 存在する場合 → 既存ノードを再利用                      │
│                                                             │
│  4️⃣ Memory → Context のリレーション作成                     │
│     CREATE (m)-[:ORIGINATED_IN]->(c)                        │
│                                                             │
│  5️⃣ 各タグに対して繰り返し:                                 │
│     a. Tag ノードを MERGE                                   │
│     b. Memory → Tag のリレーション作成                       │
│        CREATE (m)-[:TAGGED_WITH]->(t)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 update_memory の処理フロー

```
┌─────────────────────────────────────────────────────────────┐
│                    update_memory 実行                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  contentが指定された場合:                                   │
│  1️⃣ 新しいコンテンツをベクトル化                            │
│  2️⃣ Memory.content, summary, embedding, updated_at を更新  │
│                                                             │
│  tagsが指定された場合:                                      │
│  3️⃣ 既存のTAGGED_WITH リレーションを全削除                  │
│  4️⃣ 新しいタグでTag MERGE + TAGGED_WITH 作成               │
│                                                             │
│  memory_typeが指定された場合:                               │
│  5️⃣ Memory.memory_type, updated_at を更新                  │
│                                                             │
│  ※ RELATED_TO リンクは維持される                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. グラフ探索（explore_related）

### 4.1 探索の3つの軸

`explore_related` は、指定した記憶から3つの方法で関連記憶を発見します：

```
                         ┌─────────────────────┐
                         │  指定した Memory    │
                         │   (中心ノード)      │
                         └──────────┬──────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │   linked      │      │   by_tag      │      │  by_context   │
    │  (直接リンク)  │      │ (同じタグ)    │      │ (同じContext) │
    └───────────────┘      └───────────────┘      └───────────────┘
         │                       │                       │
         │                       │                       │
    RELATED_TO で          TAGGED_WITH で         ORIGINATED_IN で
    接続された記憶          共通のTagを持つ         同じContextに属する
                           記憶を発見              記憶を発見
```

### 4.2 Cypherクエリの例

#### 直接リンクされた記憶

```cypher
MATCH (m:Memory {id: $id})-[r:RELATED_TO]->(linked:Memory)
OPTIONAL MATCH (linked)-[:ORIGINATED_IN]->(c:Context)
OPTIONAL MATCH (linked)-[:TAGGED_WITH]->(t:Tag)
RETURN linked, c.name, collect(t.name) as tags,
       r.relation_type, r.reason
```

#### 同じタグを持つ記憶（タグ兄弟）

```cypher
MATCH (m:Memory {id: $id})-[:TAGGED_WITH]->(t:Tag)<-[:TAGGED_WITH]-(sibling:Memory)
WHERE m <> sibling
RETURN sibling, collect(DISTINCT t.name) as shared_tags
ORDER BY size(shared_tags) DESC
```

#### 同じContextの記憶（コンテキスト兄弟）

```cypher
MATCH (m:Memory {id: $id})-[:ORIGINATED_IN]->(c:Context)<-[:ORIGINATED_IN]-(sibling:Memory)
WHERE m <> sibling
RETURN sibling, c.name
ORDER BY sibling.created_at DESC
```

---

## 5. グラフの成長パターン

### 5.1 知識ネットワークの構築

```
【Step 1: 最初の記憶】
┌──────────────────────┐
│ Memory-1 (principle) │ ─── backend-project
│ "Connection pooling" │ ─── [database, performance]
└──────────────────────┘

【Step 2: 適用例を追加してリンク】
┌──────────────────────┐
│ Memory-1 (principle) │ ─── backend-project
│ "Connection pooling" │ ─── [database, performance]
└──────────▲───────────┘
           │ RELATED_TO (extends)
           │
┌──────────┴───────────┐
│ Memory-2 (success)   │ ─── backend-project
│ "PostgreSQL pooling" │ ─── [database, postgresql]
└──────────────────────┘

【Step 3: 別プロジェクトでも適用】
┌──────────────────────┐
│ Memory-1 (principle) │ ─── backend-project
│ "Connection pooling" │ ─── [database, performance]
└──────────▲───────────┘
           │
    ┌──────┴──────┐
    │             │
    │ RELATED_TO  │ RELATED_TO
    │ (extends)   │ (extends)
    │             │
┌───┴──────────┐  │
│ Memory-2     │  │
│ PostgreSQL   │  │
└──────────────┘  │
                  │
           ┌──────┴───────┐
           │ Memory-3     │ ─── cache-service  ← 別プロジェクト
           │ Redis pool   │ ─── [redis, performance]
           └──────────────┘
                  │
                  │ 同じ "performance" タグで
                  │ Memory-1, Memory-2 と暗黙的に関連！
```

### 5.2 MERGE による効率的なグラフ管理

```
【MERGEの動作】

同じタグを持つ記憶が追加される場合：

Memory-1 ──TAGGED_WITH──┐
                        │
                        ▼
                   ┌─────────┐
                   │  python │  ← 1つのノードを共有
                   └─────────┘
                        ▲
                        │
Memory-2 ──TAGGED_WITH──┘

→ タグ経由で自然に関連付けられる
```

---

## 6. データの整合性

### 6.1 削除時の処理

```
┌─────────────────────────────────────────────────────────────┐
│                    delete_memory 実行                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ ORIGINATED_IN リレーションを削除                        │
│     (Memory → Context)                                     │
│                                                             │
│  2️⃣ TAGGED_WITH リレーションを削除                          │
│     (Memory → Tag)                                         │
│                                                             │
│  3️⃣ RELATED_TO リレーションを削除（双方向）                  │
│     (Memory → 他のMemory)                                  │
│     (他のMemory → Memory)                                  │
│                                                             │
│  4️⃣ Memory ノード自体を削除                                 │
│                                                             │
│  ※ Context, Tag ノードは削除しない                         │
│    （他のMemoryが参照している可能性があるため）              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 スキーマの初期化

```sql
-- ノードテーブル
CREATE NODE TABLE IF NOT EXISTS Memory (
    id STRING PRIMARY KEY,
    content STRING,
    summary STRING,
    embedding FLOAT[384],
    memory_type STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

CREATE NODE TABLE IF NOT EXISTS Context (
    name STRING PRIMARY KEY,
    created_at TIMESTAMP
)

CREATE NODE TABLE IF NOT EXISTS Tag (
    name STRING PRIMARY KEY,
    created_at TIMESTAMP
)

-- リレーションテーブル
CREATE REL TABLE IF NOT EXISTS ORIGINATED_IN (FROM Memory TO Context)
CREATE REL TABLE IF NOT EXISTS TAGGED_WITH (FROM Memory TO Tag)
CREATE REL TABLE IF NOT EXISTS RELATED_TO (
    FROM Memory TO Memory,
    relation_type STRING,
    reason STRING,
    created_at TIMESTAMP
)
```

---

## 7. 検索メカニズム

### 7.1 セマンティック検索（recall_memories）

```
┌────────────────────────────────────────────────────┐
│               recall_memories の流れ               │
├────────────────────────────────────────────────────┤
│                                                    │
│  1. クエリをベクトル化                              │
│     "async debugging" → [0.12, -0.05, ...]        │
│                                                    │
│  2. 全Memoryノードのembeddingと比較                │
│     cosine_similarity(query_vec, memory_vec)       │
│                                                    │
│  3. フィルタ適用（オプション）                      │
│     - context_filter: 特定プロジェクトに絞る       │
│     - tag_filter: 特定タグを含む記憶に絞る         │
│     - type_filter: 特定のmemory_typeに絞る         │
│                                                    │
│  4. 類似度でソート → 上位N件を返却                  │
│                                                    │
│  5. 各MemoryのContext, Tagsも取得して返却           │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 7.2 グラフ探索（explore_related）

```
┌────────────────────────────────────────────────────┐
│               explore_related の流れ               │
├────────────────────────────────────────────────────┤
│                                                    │
│  1. 指定されたMemoryを中心ノードとして設定          │
│                                                    │
│  2. RELATED_TO で直接リンクされた記憶を取得         │
│                                                    │
│  3. TAGGED_WITH 経由で同じタグを持つ記憶を取得      │
│     (共有タグ数でソート)                           │
│                                                    │
│  4. ORIGINATED_IN 経由で同じContextの記憶を取得     │
│     (作成日時でソート)                             │
│                                                    │
│  5. 重複を除去して返却                              │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## まとめ

| 特徴 | 説明 |
|------|------|
| **プロパティグラフ** | ノードとリレーションで知識を構造化 |
| **Memory間リンク** | 明示的な関連付けでナレッジネットワーク構築 |
| **MERGE パターン** | 重複なく効率的にグラフを成長 |
| **ベクトル埋め込み** | セマンティック検索を実現 |
| **グラフ探索** | リンク・タグ・コンテキスト経由で関連発見 |
| **拡張性** | Cypherクエリで高度なグラフ探索が可能 |

Exocortexは、ベクトル検索の即時性とグラフ構造の関連性を組み合わせることで、
開発者の「外部脳」として効果的に機能します。
