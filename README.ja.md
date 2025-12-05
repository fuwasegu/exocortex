# Exocortex 🧠

> "Extend your mind." - あなたの外部脳

**[English version is here](./README.md)**

---

**Exocortex** は開発者の「第二の脳」として機能するローカルMCP（Model Context Protocol）サーバーです。

開発中の知見、技術的な意思決定、トラブルシューティングの記録を永続化し、AIアシスタント（Cursor等）が必要なタイミングで文脈に合わせて記憶を引き出せるようにします。

## なぜ Exocortex？

### 🌐 プロジェクト横断型の知識共有

リポジトリごとにデータを管理するツール（例：`.serena/`）とは異なり、**Exocortexは単一の集中型ナレッジストアを使用**します。

```
従来のアプローチ（リポジトリ単位）:
project-A/.serena/    ← 孤立した知識
project-B/.serena/    ← 孤立した知識
project-C/.serena/    ← 孤立した知識

Exocortexのアプローチ（集中型）:
~/.exocortex/data/    ← すべてのプロジェクトで共有
    ├── project-Aからの知見
    ├── project-Bからの知見
    └── project-Cからの知見
        ↓
    プロジェクト横断の学習！
```

**メリット:**
- 🔄 **知識の転用**: あるプロジェクトで得た教訓が、他のプロジェクトですぐに活用可能
- 🏷️ **タグベースの発見**: 共通のタグを通じて、プロジェクトを跨いで関連記憶を検索
- 📈 **累積的な学習**: 外部脳はプロジェクト単位ではなく、時間と共に賢くなる
- 🔍 **パターン認識**: 開発履歴全体から共通の問題と解決策を発見

## 特徴

- 🔒 **ローカル完結**: すべてのデータとAI処理がローカルで完結。プライバシーを確保
- 🔍 **セマンティック検索**: キーワードではなく意味で記憶を検索
- 🕸️ **知識グラフ**: プロジェクト、タグ、記憶の関連性をグラフ構造で保持
- 🔗 **記憶のリンク**: 関連する記憶を明示的に接続し、知識ネットワークを構築
- ⚡ **軽量・高速**: 組み込みDB（KùzuDB）と軽量Embeddingモデル（fastembed）を採用

## インストール

```bash
# リポジトリをクローン
git clone https://github.com/fuwasegu/exocortex.git
cd exocortex

# uvで依存関係をインストール
uv sync
```

## 使い方

### サーバーの起動

```bash
uv run exocortex
```

### Cursorでの設定

`~/.cursor/mcp.json` に以下を追加:

#### 方法1: GitHubから直接実行（推奨）

uvx のキャッシュ期限切れ時に自動更新。手動の `git pull` 不要。

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

#### 方法2: ローカルインストール

開発やカスタマイズ用。

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

> **Note:** データは `~/.exocortex/` に保存され、どちらの方法でも保持されます。

## MCPツール

### 基本ツール

| ツール | 説明 |
|--------|------|
| `exo_ping` | サーバーの疎通確認 |
| `exo_store_memory` | 新しい記憶を保存 |
| `exo_recall_memories` | セマンティック検索で関連する記憶を想起 |
| `exo_list_memories` | 記憶の一覧を取得（ページネーション対応） |
| `exo_get_memory` | IDを指定して特定の記憶を取得 |
| `exo_delete_memory` | 記憶を削除 |
| `exo_get_stats` | 統計情報を取得 |

### 高度なツール

| ツール | 説明 |
|--------|------|
| `exo_link_memories` | 2つの記憶をリンク（関連付け） |
| `exo_unlink_memories` | リンクを削除 |
| `exo_update_memory` | 記憶の内容・タグ・タイプを更新 |
| `exo_explore_related` | グラフ探索で関連記憶を発見 |
| `exo_get_memory_links` | 記憶のリンク一覧を取得 |
| `exo_analyze_knowledge` | 知識ベースの健全性分析と改善提案 |

### 🤖 知識の自律的改善（Knowledge Autonomy）

Exocortexは知識グラフを自動的に改善します！記憶を保存すると、システムが：

1. **リンクを提案**: 類似した既存の記憶を見つけて接続を提案
2. **重複を検出**: 既存の記憶と類似しすぎている場合に警告
3. **パターンを認識**: 成功が過去の失敗を解決したことを認識

```json
// exo_store_memory のレスポンス例（提案付き）
{
  "success": true,
  "memory_id": "...",
  "suggested_links": [
    {
      "target_id": "existing-memory-id",
      "similarity": 0.78,
      "suggested_relation": "extends",
      "reason": "高い意味的類似性; この知見の応用例の可能性"
    }
  ],
  "insights": [
    {
      "type": "potential_duplicate",
      "message": "この記憶は既存のものと非常に類似しています (94%)",
      "suggested_action": "代わりに exo_update_memory を使用してください"
    }
  ]
}
```

### リレーションタイプ（`exo_link_memories`用）

| タイプ | 説明 |
|--------|------|
| `related` | 一般的に関連 |
| `supersedes` | この記憶が対象を更新/置換 |
| `contradicts` | この記憶が対象と矛盾 |
| `extends` | この記憶が対象を拡張/詳細化 |
| `depends_on` | この記憶が対象に依存 |

## 環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `EXOCORTEX_DATA_DIR` | `./data` | データベース保存先 |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | ログレベル（DEBUG/INFO/WARNING/ERROR） |
| `EXOCORTEX_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 使用するEmbeddingモデル |

## アーキテクチャ

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

### 知識グラフの構造

```
Memory ─── ORIGINATED_IN ──► Context（プロジェクト）
Memory ─── TAGGED_WITH ────► Tag
Memory ─── RELATED_TO ─────► Memory（リレーションタイプ付き）
```

## ドキュメント

- [設計書](./docs/design_doc.md) - システム設計と仕様
- [グラフアーキテクチャ](./docs/graph_architecture.md) - 知識グラフの仕組み

## 開発

```bash
# 依存関係のインストール
uv sync

# テストの実行
uv run pytest

# デバッグログを有効にして実行
EXOCORTEX_LOG_LEVEL=DEBUG uv run exocortex
```

## ライセンス

MIT License
