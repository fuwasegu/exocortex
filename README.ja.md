# Exocortex 🧠

> "Extend your mind." - あなたの外部脳

**[English version is here](./README.md)**

---

**Exocortex** は開発者の「第二の脳」として機能するローカルMCP（Model Context Protocol）サーバーです。

開発中の知見、技術的な意思決定、トラブルシューティングの記録を永続化し、AIアシスタント（Cursor等）が必要なタイミングで文脈に合わせて記憶を引き出せるようにします。

## 特徴

- 🔒 **ローカル完結**: すべてのデータとAI処理がローカルで完結。プライバシーを確保
- 🔍 **セマンティック検索**: キーワードではなく意味で記憶を検索
- 🕸️ **グラフ構造**: プロジェクト、タグ、記憶の関連性を保持
- ⚡ **軽量・高速**: 組み込みDB（KùzuDB）と軽量Embeddingモデル（fastembed）を採用

## インストール

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/exocortex.git
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

## MCPツール

| ツール | 説明 |
|--------|------|
| `ping` | サーバーの疎通確認 |
| `store_memory` | 新しい記憶を保存 |
| `recall_memories` | セマンティック検索で関連する記憶を想起 |
| `list_memories` | 記憶の一覧を取得 |
| `get_memory` | IDを指定して特定の記憶を取得 |
| `delete_memory` | 記憶を削除 |
| `get_stats` | 統計情報を取得 |

## 環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `EXOCORTEX_DATA_DIR` | `./data` | データベース保存先 |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | ログレベル（DEBUG/INFO/WARNING/ERROR） |
| `EXOCORTEX_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 使用するEmbeddingモデル |

## 開発

```bash
# 依存関係のインストール
uv sync

# テストの実行
uv run pytest

# デバッグログを有効にして実行
EXOCORTEX_LOG_LEVEL=DEBUG uv run exocortex
```

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

## ライセンス

MIT License

