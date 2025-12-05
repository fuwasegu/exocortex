# Exocortex (外部脳) MCPサーバー 設計書

## 1. 概要

**Exocortex** は、開発者の「第二の脳」として機能するローカルMCPサーバーである。
開発中の知見、技術的な意思決定、トラブルシューティングの記録を永続化し、AIアシスタント（Cursor等）が必要なタイミングで文脈に合わせて記憶を引き出せるようにする。

**コンセプト:** "Extend your mind."（脳の拡張）

### 1.1 設計原則

1. **ローカル完結**: すべての処理をローカルで完結させ、プライバシーを確保する
2. **シンプルさ**: 最小限の依存関係で、理解しやすいアーキテクチャを維持する
3. **セマンティック**: 単なるキーワード検索ではなく、意味的な類似性で記憶を想起する
4. **コンテキスト重視**: 記憶を孤立させず、プロジェクトやタグとの関連性を保持する

---

## 2. ユースケース

### UC-1: 問題解決の記録
- **アクター:** 開発者（AIアシスタント経由）
- **トリガー:** バグ修正やトラブルシューティングが完了した時
- **シナリオ:**
  1. 開発者が「このバグの原因と解決策をExocortexに記憶して」と指示
  2. AIが `store_memory` を呼び出し、解決策を構造化して保存
  3. 関連タグ（使用技術）とコンテキスト（プロジェクト名）が自動的に紐付けられる
- **期待結果:** Memory(type=Success)として永続化される

### UC-2: 過去知見の想起
- **アクター:** 開発者（AIアシスタント経由）
- **トリガー:** 類似の問題に遭遇した時
- **シナリオ:**
  1. 開発者が「async/awaitでデッドロックになる。過去に似た問題はあった？」と質問
  2. AIが `recall_memories` を呼び出し、セマンティック検索を実行
  3. 類似度の高い記憶がコンテキスト情報付きで返却される
- **期待結果:** 過去の解決策が文脈付きで提示され、問題解決が加速する

### UC-3: プロジェクト横断の知識活用
- **アクター:** 開発者
- **トリガー:** 別プロジェクトで同じ技術を使う時
- **シナリオ:**
  1. プロジェクトAで「FastAPI + SQLAlchemy」の知見を記憶
  2. プロジェクトBで同じ技術スタックを使用開始
  3. `recall_memories` でタグ「FastAPI」に関連する記憶を横断検索
- **期待結果:** プロジェクトを跨いだ知識の再利用が可能

### UC-4: 失敗パターンの学習
- **アクター:** 開発者
- **トリガー:** 同じミスを繰り返しそうな時
- **シナリオ:**
  1. 過去に「N+1問題」で失敗した記録が Memory(type=Failure) として保存済み
  2. 新しいコードでORMを使う際、AIが関連する失敗記憶を想起
  3. 過去の失敗パターンを踏まえた提案を行う
- **期待結果:** 同じ失敗の繰り返しを防止

### UC-5: 記憶の管理・メンテナンス
- **アクター:** 開発者
- **トリガー:** 記憶の整理・確認が必要な時
- **シナリオ:**
  1. 開発者が「Exocortexに保存されている記憶を一覧表示して」と指示
  2. AIが `list_memories` を呼び出し、記憶の概要リストを取得
  3. 不要な記憶があれば `delete_memory` で削除
- **期待結果:** 記憶の品質を維持できる

### UC-6: 知識のリンクと探索
- **アクター:** 開発者（AIアシスタント経由）
- **トリガー:** 関連する知識を明示的に紐付けたい時
- **シナリオ:**
  1. 開発者が「さっきの解決策は、以前記録したコネクションプーリングの原則の適用例だね」と指示
  2. AIが `link_memories` を呼び出し、2つの記憶をリンク（relation_type: "extends"）
  3. 後日、原則の記憶から `explore_related` で関連記憶を探索
  4. リンクされた適用例が自動的に表示される
- **期待結果:** 知識ネットワークが構築され、関連情報の発見が容易になる

### UC-7: 記憶の更新と進化
- **アクター:** 開発者
- **トリガー:** 既存の記憶に追記や修正が必要な時
- **シナリオ:**
  1. 以前記録した知見に新しい情報を追加したい
  2. AIが `update_memory` を呼び出し、内容を更新
  3. ベクトル埋め込みも自動的に再計算される
- **期待結果:** 記憶が進化し、常に最新の知識を反映

---

## 3. アーキテクチャ

### 3.1 システム構成

```
┌─────────────────┐     stdio      ┌─────────────────────────────┐
│  AIアシスタント  │ ◄──────────► │       Exocortex MCP         │
│   (Cursor等)    │    MCP        │                             │
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

### 3.2 技術スタック

| コンポーネント | 技術 | 選定理由 |
|---------------|------|----------|
| 配布形態 | Pythonパッケージ (`uv`管理) | 依存関係管理が容易、高速 |
| 通信プロトコル | MCP over Stdio | シンプル、プロセス間通信に最適 |
| データベース | KùzuDB | グラフ+ベクトル両対応、組み込み型 |
| Embedding | fastembed | ローカル完結、軽量、高速 |
| Embeddingモデル | `BAAI/bge-small-en-v1.5` | 384次元、多言語対応、軽量 |

### 3.3 実行モデル

```bash
# 起動コマンド
uv --directory /path/to/exocortex run exocortex

# Cursor MCP設定例
{
  "mcpServers": {
    "exocortex": {
      "command": "uv",
      "args": ["--directory", "/path/to/exocortex", "run", "exocortex"]
    }
  }
}
```

---

## 4. データベース設計 (KùzuDBスキーマ)

### 4.1 ノード (Nodes)

#### Memory (記憶)
外部脳に保存される知識の最小単位。

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `id` | STRING | UUID (Primary Key) |
| `content` | STRING | Markdown形式の知識本文 |
| `summary` | STRING | 検索一覧用の要約（contentの先頭200文字から自動生成） |
| `embedding` | FLOAT[384] | ベクトルデータ |
| `type` | STRING | 記憶の種類（下記Enum参照） |
| `created_at` | TIMESTAMP | 作成日時 |
| `updated_at` | TIMESTAMP | 更新日時 |

**Memory Type (Enum):**
- `insight`: 一般的な知見・学び
- `success`: 成功した解決策
- `failure`: 失敗とその原因
- `decision`: 技術的な意思決定とその理由
- `note`: その他のメモ

#### Context (コンテキスト)
記憶が形成された状況やプロジェクト背景。

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `name` | STRING | Primary Key (例: "exocortex-dev") |
| `created_at` | TIMESTAMP | 作成日時 |

#### Tag (タグ)
関連する技術要素や概念。

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `name` | STRING | Primary Key (例: "Python", "GraphDB") |
| `created_at` | TIMESTAMP | 作成日時 |

### 4.2 リレーション (Edges)

```cypher
(:Memory)-[:ORIGINATED_IN]->(:Context)  // 記憶 → 形成されたコンテキスト
(:Memory)-[:TAGGED_WITH]->(:Tag)        // 記憶 → 関連タグ
(:Memory)-[:RELATED_TO]->(:Memory)      // 記憶 → 関連する記憶
```

#### RELATED_TO リレーションのプロパティ

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `relation_type` | STRING | リレーションの種類（下記参照） |
| `reason` | STRING | リンクの理由（オプション） |
| `created_at` | TIMESTAMP | 作成日時 |

**Relation Type (Enum):**
- `related`: 一般的な関連
- `supersedes`: この記憶が対象を更新/置換
- `contradicts`: この記憶が対象と矛盾
- `extends`: この記憶が対象を拡張/詳細化
- `depends_on`: この記憶が対象に依存

### 4.3 インデックス

```cypher
// ベクトル検索用インデックス
CREATE VECTOR INDEX memory_embedding_index ON Memory(embedding)
```

---

## 5. MCPツール定義

### 5.1 store_memory (記憶する)

新しい知見をExocortexに永続化する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `content` | string | ✓ | 記憶する内容の詳細（Markdown可） |
| `context_name` | string | ✓ | 現在のプロジェクトや状況名 |
| `tags` | string[] | ✓ | 関連キーワードのリスト |
| `memory_type` | string | | 記憶の種類（デフォルト: "insight"） |

**戻り値:**
```json
{
  "success": true,
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "summary": "生成された要約文..."
}
```

**処理フロー:**
1. `content` から要約（summary）を生成（先頭200文字）
2. `content` をベクトル化
3. `Context`, `Tag` ノードを `MERGE`（存在しなければ作成）
4. `Memory` ノードを `CREATE`
5. リレーションを構築

---

### 5.2 recall_memories (想起する)

現在の課題に関連する過去の記憶を、ハイブリッド検索で呼び覚ます。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `query` | string | ✓ | 想起したい内容のクエリ |
| `limit` | int | | 取得件数（デフォルト: 5、最大: 20） |
| `context_filter` | string | | 特定のコンテキストに絞る |
| `tag_filter` | string[] | | 特定のタグを含む記憶に絞る |
| `type_filter` | string | | 特定のtypeに絞る |

**戻り値:**
```json
{
  "memories": [
    {
      "id": "...",
      "summary": "...",
      "content": "...",
      "type": "success",
      "similarity": 0.87,
      "context": "project-name",
      "tags": ["Python", "async"],
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total_found": 3
}
```

**処理フロー:**
1. `query` をベクトル化
2. ベクトル類似検索（`CALL nn_search`）で候補を抽出
3. フィルタ条件を適用
4. ヒットした記憶に紐づく `Context`, `Tag` を取得
5. 構造化して返却

---

### 5.3 list_memories (一覧取得)

保存されている記憶の一覧を取得する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `limit` | int | | 取得件数（デフォルト: 20） |
| `offset` | int | | オフセット（デフォルト: 0） |
| `context_filter` | string | | 特定のコンテキストに絞る |
| `tag_filter` | string[] | | 特定のタグを含む記憶に絞る |
| `type_filter` | string | | 特定のtypeに絞る |

**戻り値:**
```json
{
  "memories": [
    {
      "id": "...",
      "summary": "...",
      "type": "insight",
      "context": "project-name",
      "tags": ["Python"],
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total_count": 42,
  "has_more": true
}
```

---

### 5.4 get_memory (詳細取得)

特定の記憶の詳細を取得する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `memory_id` | string | ✓ | 取得する記憶のID |

**戻り値:**
```json
{
  "id": "...",
  "content": "完全な内容...",
  "summary": "...",
  "type": "success",
  "context": "project-name",
  "tags": ["Python", "async"],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-16T14:20:00Z"
}
```

---

### 5.5 delete_memory (削除)

指定した記憶を削除する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `memory_id` | string | ✓ | 削除する記憶のID |

**戻り値:**
```json
{
  "success": true,
  "deleted_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 5.6 get_stats (統計情報)

Exocortexの統計情報を取得する。

**引数:** なし

**戻り値:**
```json
{
  "total_memories": 42,
  "memories_by_type": {
    "insight": 20,
    "success": 15,
    "failure": 5,
    "decision": 2
  },
  "total_contexts": 5,
  "total_tags": 23,
  "top_tags": [
    {"name": "Python", "count": 18},
    {"name": "async", "count": 12}
  ]
}
```

---

### 5.7 link_memories (記憶をリンク)

2つの記憶を明示的にリンクする。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `source_id` | string | ✓ | リンク元の記憶ID |
| `target_id` | string | ✓ | リンク先の記憶ID |
| `relation_type` | string | ✓ | リレーションの種類 |
| `reason` | string | | リンクの理由 |

**戻り値:**
```json
{
  "success": true,
  "source_id": "...",
  "target_id": "...",
  "relation_type": "extends"
}
```

---

### 5.8 unlink_memories (リンク解除)

記憶間のリンクを削除する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `source_id` | string | ✓ | リンク元の記憶ID |
| `target_id` | string | ✓ | リンク先の記憶ID |

**戻り値:**
```json
{
  "success": true
}
```

---

### 5.9 update_memory (記憶を更新)

既存の記憶を更新する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `memory_id` | string | ✓ | 更新する記憶のID |
| `content` | string | | 新しい内容 |
| `tags` | string[] | | 新しいタグ（指定時は置換） |
| `memory_type` | string | | 新しい種類 |

**戻り値:**
```json
{
  "success": true,
  "memory_id": "...",
  "changes": ["content", "tags"]
}
```

**処理フロー:**
1. `content` が指定された場合、新しいベクトルを生成
2. `tags` が指定された場合、既存のTAGGED_WITHを削除し新規作成
3. `updated_at` を更新

---

### 5.10 explore_related (関連記憶を探索)

指定した記憶から関連する記憶をグラフ探索で発見する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `memory_id` | string | ✓ | 中心となる記憶のID |
| `include_tag_siblings` | bool | | 同じタグを持つ記憶を含める（デフォルト: true） |
| `include_context_siblings` | bool | | 同じContextの記憶を含める（デフォルト: true） |

**戻り値:**
```json
{
  "memory_id": "...",
  "linked": [
    {
      "id": "...",
      "summary": "...",
      "relation_type": "extends",
      "reason": "具体的な適用例"
    }
  ],
  "by_tag": [
    {
      "id": "...",
      "summary": "...",
      "shared_tags": ["Python", "async"]
    }
  ],
  "by_context": [
    {
      "id": "...",
      "summary": "...",
      "context": "project-name"
    }
  ]
}
```

---

### 5.11 get_memory_links (リンク一覧取得)

指定した記憶からの出発リンクを取得する。

**引数:**

| 名前 | 型 | 必須 | 説明 |
|------|-----|------|------|
| `memory_id` | string | ✓ | 記憶のID |

**戻り値:**
```json
{
  "memory_id": "...",
  "links": [
    {
      "target_id": "...",
      "target_summary": "...",
      "relation_type": "extends",
      "reason": "PostgreSQLへの具体的な適用例",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### 5.12 analyze_knowledge (知識分析)

知識ベースの健全性を分析し、改善提案を行う。

**引数:** なし

**戻り値:**
```json
{
  "total_memories": 42,
  "health_score": 85.0,
  "issues": [
    {
      "type": "orphan_memories",
      "severity": "medium",
      "message": "5 memories have no tags",
      "affected_memory_ids": ["...", "..."],
      "suggested_action": "Add tags using update_memory"
    },
    {
      "type": "low_connectivity",
      "severity": "low",
      "message": "80% of memories have no explicit links",
      "suggested_action": "Use explore_related and link_memories"
    }
  ],
  "suggestions": [
    "Address issues above to improve discoverability",
    "Don't forget to record failures too!"
  ],
  "stats": {
    "unlinked_memories": 34,
    "memories_per_context": {"project-a": 20, "project-b": 22}
  }
}
```

**検出する問題:**
- `orphan_memories`: タグのない記憶
- `low_connectivity`: リンクの少なさ
- `stale_memories`: 長期間更新されていない記憶
- `similar_tags`: 正規化が必要な類似タグ

---

### 5.13 store_memory の自動分析機能

`store_memory` は記憶を保存した後、自動的に以下を分析して戻り値に含める:

**追加フィールド:**

| フィールド | 説明 |
|------------|------|
| `suggested_links` | 類似度の高い既存記憶へのリンク提案 |
| `insights` | 重複検出、矛盾検出などの知見 |

**戻り値の例:**
```json
{
  "success": true,
  "memory_id": "...",
  "summary": "...",
  "suggested_links": [
    {
      "target_id": "existing-id",
      "target_summary": "Related principle...",
      "similarity": 0.78,
      "suggested_relation": "extends",
      "reason": "High semantic similarity; may be an application of this insight"
    }
  ],
  "insights": [
    {
      "type": "potential_duplicate",
      "message": "This memory is very similar (94%) to an existing one",
      "related_memory_id": "...",
      "confidence": 0.94,
      "suggested_action": "Use update_memory instead"
    }
  ],
  "link_suggestion_message": "Found 2 related memories. Consider linking them."
}
```

**インサイトの種類:**
- `potential_duplicate`: 非常に類似した既存記憶の検出 (類似度 > 90%)
- `potential_contradiction`: 矛盾の可能性がある記憶の検出
- `success_after_failure`: 成功が過去の失敗を解決した可能性

---

## 6. 非機能要件

### 6.1 パフォーマンス

| 項目 | 目標値 | 備考 |
|------|--------|------|
| サーバー起動時間 | 3秒以内 | Embeddingモデルの遅延ロード採用 |
| `store_memory` 応答 | 1秒以内 | Embedding生成含む |
| `recall_memories` 応答 | 500ms以内 | 1,000記憶時 |
| メモリ使用量 | 500MB以内 | モデルロード時 |

### 6.2 スケーラビリティ

- **想定記憶数:** 10,000件程度（個人開発者のローカル用途）
- **ベクトル検索:** KùzuDBのネイティブ `nn_search` を使用（HNSW）

### 6.3 信頼性

- **データ永続化:** KùzuDBのファイルベースストレージ（WAL対応）
- **バックアップ:** `data/` フォルダのコピーで完結
- **クラッシュリカバリ:** KùzuDBのトランザクション機能に依存

### 6.4 運用性

- **ログ出力:** stderr経由でログ出力（MCPプロトコル準拠）
- **ログレベル:** 環境変数 `EXOCORTEX_LOG_LEVEL` で制御
- **データ場所:** 環境変数 `EXOCORTEX_DATA_DIR` でカスタマイズ可能

### 6.5 セキュリティ

- **ローカル完結:** すべての処理をローカルで実行、外部通信なし
- **データ保護:** ユーザーのローカルディスクにのみ保存
- **アクセス制御:** ファイルシステムのパーミッションに依存

---

## 7. 設定

### 7.1 環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `EXOCORTEX_DATA_DIR` | `./data` | データベース保存先 |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | ログレベル (DEBUG/INFO/WARNING/ERROR) |
| `EXOCORTEX_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 使用するEmbeddingモデル |

### 7.2 設定ファイル（将来拡張用）

```toml
# exocortex.toml (オプション)
[database]
path = "./data"

[embedding]
model = "BAAI/bge-small-en-v1.5"

[logging]
level = "INFO"
```

---

## 8. ディレクトリ構成

```text
exocortex/
├── data/                   # KùzuDB データストア (gitignored)
├── docs/
│   └── design_doc.md       # 本設計書
├── src/
│   └── exocortex/
│       ├── __init__.py
│       ├── main.py         # エントリポイント (MCPサーバー起動)
│       ├── server.py       # MCPサーバー定義・ツール登録
│       ├── db.py           # KùzuDB ラッパー
│       ├── embeddings.py   # Embeddingエンジン
│       ├── models.py       # データモデル定義
│       └── config.py       # 設定管理
├── tests/
│   ├── __init__.py
│   ├── test_db.py
│   ├── test_embeddings.py
│   └── test_tools.py
├── pyproject.toml
└── README.md
```

---

## 9. 実装計画

### Phase 1: 基盤構築
**目標:** MCPサーバーの骨格を作成し、疎通確認を行う。

1. プロジェクト構造の整備
   - `src/exocortex/` パッケージ作成
   - `pyproject.toml` 更新（エントリポイント修正）
2. 設定管理 (`config.py`)
   - 環境変数の読み込み
3. MCPサーバー起動 (`main.py`, `server.py`)
   - Stdioモードでのサーバー起動
   - `ping` ツール実装（疎通確認用）
4. 接続テスト
   - ターミナルでの起動確認
   - Cursor設定での認識確認

### Phase 2: データ層実装
**目標:** KùzuDBとEmbeddingエンジンを実装する。

1. Embeddingエンジン (`embeddings.py`)
   - fastembed の初期化（遅延ロード）
   - テキスト→ベクトル変換
2. DBラッパー (`db.py`)
   - KùzuDB初期化
   - スキーマ作成（Memory, Context, Tag, リレーション）
   - ベクトルインデックス作成
3. データモデル (`models.py`)
   - Pydanticモデル定義

### Phase 3: コアツール実装
**目標:** `store_memory` と `recall_memories` を実装する。

1. `store_memory` 実装
   - 要約生成、ベクトル化、グラフ保存
2. `recall_memories` 実装
   - ベクトル検索 + フィルタリング
   - コンテキスト・タグ取得

### Phase 4: 管理ツール実装
**目標:** CRUD操作とユーティリティツールを実装する。

1. `list_memories` 実装
2. `get_memory` 実装
3. `delete_memory` 実装
4. `get_stats` 実装

### Phase 5: 統合テスト
**目標:** AIアシスタントとの連携を確認する。

1. 記憶テスト: 知見の保存と想起
2. フィルタテスト: コンテキスト・タグ・タイプでの絞り込み
3. エッジケーステスト: 空の状態、大量データ等

---

## 10. 将来の拡張案（v2以降）

### 実装済み ✅
- ~~**`update_memory`**: 既存記憶の更新~~
- ~~**記憶の関連付け**: `(:Memory)-[:RELATED_TO]->(:Memory)`~~
- ~~**グラフ探索**: `explore_related` による関連記憶の発見~~
- ~~**知識の自律的改善**: `store_memory` 時の自動リンク提案・重複検出~~
- ~~**知識分析**: `analyze_knowledge` による健全性チェック~~

### 検討中
- **`merge_memories`**: 類似記憶の統合
- **エクスポート/インポート**: JSONでのバックアップ・復元
- **Web UI**: 記憶の可視化・ブラウジング
- **記憶の鮮度管理**: 古い記憶の重要度低下・アーカイブ
- **マルチモーダル対応**: 画像・図の埋め込みと検索
- **自動タグ提案**: 内容からタグを自動推論
