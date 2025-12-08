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
- 🧠 **Memory Dynamics**: 鮮度と頻度に基づくスマートな想起—頻繁にアクセスされる記憶が上位に
- 🖥️ **Webダッシュボード**: サイバーパンク風のUIで記憶の閲覧、健全性の監視、知識グラフの可視化が可能

## 📚 使い方ガイド

**→ [詳しい使い方はこちら](./manuals/usage-guide.ja.md)**

- ツール一覧とユースケース
- 実践的なワークフロー
- プロンプトのコツ
- Tips & Tricks

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

#### 方法3: プロキシモード（複数のCursorインスタンス対応・推奨）

**複数のCursorウィンドウから同時にExocortexを使用したい場合は、この方法を使用してください。**

KùzuDBは複数プロセスからの同時書き込みをサポートしていないため、各Cursorインスタンスが独自のサーバープロセスを起動するstdio方式では、ロック競合が発生します。プロキシモードでは、バックグラウンドで単一のSSEサーバーを自動起動し、各Cursorインスタンスはそのサーバーにプロキシ接続します。

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

**動作の流れ:**
1. 最初のCursorがExocortexを起動 → SSEサーバーが自動的にバックグラウンドで起動
2. 以降のCursorは既存のSSEサーバーに接続
3. 全てのCursorが同じサーバーを共有 → ロック競合なし！

> **Note:** 手動でのサーバー起動は不要です。`--ensure-server` オプションにより、サーバーが起動していなければ自動的に起動します。

#### 方法4: 手動サーバー管理（上級者向け）

サーバーを手動で管理したい場合：

**Step 1: サーバーを起動**

```bash
# ターミナルでサーバーを起動（バックグラウンドで実行することも可能）
uv run --directory /path/to/exocortex exocortex --transport sse --port 8765
```

**Step 2: Cursorの設定**

```json
{
  "mcpServers": {
    "exocortex": {
      "url": "http://127.0.0.1:8765/mcp/sse"
    }
  }
}
```

> **おまけ:** この設定では、`http://127.0.0.1:8765/` でWebダッシュボードにもアクセスできます

> **Tip:** サーバーをシステム起動時に自動で開始するには、macOSの場合は `launchd`、Linuxの場合は `systemd` を使用してください。

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
| `exo_sleep` | バックグラウンド整理（重複検出、孤立記憶のレスキュー）を起動 |
| `exo_consolidate` | 記憶クラスタから抽象パターンを抽出 |

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

### 🧠 自動メモリ統合（Memory Consolidation）

**人間が睡眠中に記憶を整理するように、Exocortexは記憶保存後にAIに整理を促します。**

`exo_store_memory` が成功すると、レスポンスに `next_actions` が含まれ、AIに以下を指示します：

1. **高類似度の記憶をリンク**（類似度 ≥ 0.7）
2. **重複・矛盾の処理**
3. **定期的な健全性チェック**（10件ごと）

```json
// next_actions を含むレスポンス例
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

**期待される動作フロー:**
```
ユーザー: 「この知見を記憶して」
    ↓
AI: exo_store_memory() → next_actions を受け取る
    ↓
AI: 高優先度アクションごとに exo_link_memories() を実行
    ↓
AI: 「記憶しました。2つの関連記憶とリンクしました。」
```

> ⚠️ **重要な制限事項**: `next_actions` の実行はAIエージェントの判断に委ねられます。サーバーは `SERVER_INSTRUCTIONS` と `consolidation_required: true` で強く指示しますが、**実行は100%保証されません**。これはMCPプロトコルの制限で、サーバーは提案のみ可能で強制はできません。実際には、最新のAIアシスタントの多くはこれらの指示に従いますが、複雑な会話や他のタスクとの競合時にはスキップされる可能性があります。

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
| `EXOCORTEX_DATA_DIR` | `~/.exocortex` | データベース保存先 |
| `EXOCORTEX_LOG_LEVEL` | `INFO` | ログレベル（DEBUG/INFO/WARNING/ERROR） |
| `EXOCORTEX_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | 使用するEmbeddingモデル |
| `EXOCORTEX_TRANSPORT` | `stdio` | トランスポートモード（stdio/sse/streamable-http） |
| `EXOCORTEX_HOST` | `127.0.0.1` | サーバーのバインドアドレス（HTTP時） |
| `EXOCORTEX_PORT` | `8765` | サーバーのポート番号（HTTP時） |

## アーキテクチャ

### Stdioモード（デフォルト）

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

### HTTP/SSEモード（複数インスタンス対応）

```
┌─────────────────┐                
│  Cursor #1      │──────┐         
└─────────────────┘      │         
                         │  HTTP   ┌─────────────────────────────┐
┌─────────────────┐      ├────────►│       Exocortex MCP         │
│  Cursor #2      │──────┤   SSE   │     (スタンドアロン)         │
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

### 知識グラフの構造

```
Memory ─── ORIGINATED_IN ──► Context（プロジェクト）
Memory ─── TAGGED_WITH ────► Tag
Memory ─── RELATED_TO ─────► Memory（リレーションタイプ付き）
```

### Memory Dynamics（記憶の動的管理）

Exocortexは人間の認知にインスパイアされた**Memory Dynamics**システムを実装しています。記憶には「寿命」と「強度」があり、検索結果に影響を与えます：

**ハイブリッドスコアリング式：**

```
Score = (S_vec × w_vec) + (S_recency × w_recency) + (S_freq × w_freq)
```

| コンポーネント | 説明 | デフォルト重み |
|--------------|------|--------------|
| `S_vec` | ベクトル類似度（意味的関連性） | 0.60 |
| `S_recency` | 鮮度スコア（指数減衰: e^(-λ×Δt)） | 0.25 |
| `S_freq` | 頻度スコア（対数スケール: log(1 + count)） | 0.15 |

**仕組み：**
- 記憶が想起されるたびに、`last_accessed_at`と`access_count`が更新される
- 頻繁にアクセスされる記憶は高い`S_freq`スコアを獲得
- 最近アクセスされた記憶は高い`S_recency`スコアを獲得
- 古い未使用の記憶は自然に減衰するが、検索可能なまま

これにより、以下のようなインテリジェントな想起システムが実現：
- 📈 重要な記憶（頻繁に使用）は目立ち続ける
- ⏰ 最近のコンテキストが優先される
- 🗃️ 古い記憶は緩やかにフェードするが消えない

### Sleep/Dream メカニズム

人間が睡眠中に記憶を整理するように、Exocortexにも知識グラフを整理する**バックグラウンド整理プロセス**があります：

```
┌─────────────────────────────────────────────────────────────┐
│                    exo_sleep() 呼び出し                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Dream Worker（切り離されたプロセス）            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. 重複検出                                           │   │
│  │    - 類似度 >= 95% の記憶を検出                       │   │
│  │    - 新しい方 → 古い方に 'supersedes' リンクを作成    │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 2. 孤立記憶のレスキュー                              │   │
│  │    - タグもリンクもない記憶を検出                     │   │
│  │    - 最も類似した記憶に 'related' リンクを作成       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 3. パターンマイニング（Phase 2）                      │   │
│  │    - 記憶クラスタから共通パターンを抽出              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**使い方：**
```
AI: 「タスクが完了しました。知識ベースを整理します。」
    ↓
AI: exo_sleep() → Workerがバックグラウンドで起動
    ↓
AI: 「整理プロセスを開始しました。知識グラフが最適化されます。」
```

**主な特徴：**
- 🔄 **ノンブロッキング**: 即座に戻り、整理はバックグラウンドで実行
- 🔐 **安全**: ファイルロックでアクティブセッションとの競合を防止
- 📊 **ログ**: `enable_logging=True`で進捗を追跡可能

> ⚠️ **プロキシモードでの注意事項**: プロキシモード（`--mode proxy`）を使用している場合、`exo_sleep`の使用は**推奨されません**。プロキシモードではSSEサーバーがKùzuDBへの接続を常時保持しているため、Dream Workerがバックグラウンドで起動してもデータベースにアクセスできず、タイムアウトまたは競合が発生する可能性があります。
>
> **対処法:**
> - プロキシモードでは `exo_sleep` を使用しない
> - stdioモードの場合はセッション終了前に使用可能
> - 手動でSSEサーバーを停止した後に使用する

### Pattern Abstraction（概念形成）

Exocortexは具体的な記憶から**抽象パターン**を抽出し、階層的な知識構造を作成できます：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Pattern層（抽象）                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ "データベース接続には常にコネクションプーリングを使用する" │  │
│  │ 確信度: 0.85 | インスタンス数: 5                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                    ▲ INSTANCE_OF    ▲ INSTANCE_OF
       ┌────────────┴────────────────┴────────────┐
┌──────┴──────┐  ┌───────────┐  ┌───────────┐  ┌──┴────────┐
│ Memory #1   │  │ Memory #2 │  │ Memory #3 │  │ Memory #4 │
│ PostgreSQL  │  │ MySQL     │  │ Redis     │  │ MongoDB   │
│ プーリング  │  │ pool size │  │ conn再利用│  │ pool leak │
└─────────────┘  └───────────┘  └───────────┘  └───────────┘
                     Memory層（具体）
```

**使い方：**
```
AI: exo_consolidate(tag_filter="database") → database関連の記憶からパターンを抽出
    ↓
結果: "8つの記憶から2つのパターンを作成しました"
```

**メリット：**
- 🎯 **一般化**: 個別のケースに適用できるルールを発見
- 🔍 **メタ学習**: プロジェクト横断で何がうまくいく（いかない）かを発見
- 📈 **確信度の構築**: より多くのインスタンスがリンクされるとパターンが強化

## Webダッシュボード

Exocortexには、知識ベースを可視化・管理するための美しいWebダッシュボードが付属しています。

### ダッシュボードへのアクセス

#### 🚀 プロキシモードを使っている場合（推奨）

**ターミナル操作は不要です！** プロキシモード（`--mode proxy --ensure-server`）でCursorを使っている場合、SSEサーバーは自動的にバックグラウンドで起動しています。

**ブラウザで以下を開くだけ：**

```
http://127.0.0.1:8765/
```

```
Cursor起動
    ↓
プロキシモード → SSEサーバー自動起動 (port 8765)
    ↓
├─ MCP: http://127.0.0.1:8765/mcp/sse ← Cursorが使用
└─ Dashboard: http://127.0.0.1:8765/ ← ブラウザで開くだけ！
```

#### 手動でサーバーを起動する場合

Cursorを使わずにダッシュボードだけ見たい場合は、手動でサーバーを起動：

```bash
# SSEサーバーを起動（ダッシュボード含む）
uv run exocortex --transport sse --port 8765
```

**URL:**
- **ダッシュボード**: `http://127.0.0.1:8765/`
- **MCP SSE**: `http://127.0.0.1:8765/mcp/sse`

### ダッシュボードの機能

| タブ | 説明 |
|------|------|
| **Overview** | 統計情報、コンテキスト、タグ、知識ベースの健全性スコア |
| **Memories** | 記憶の閲覧、フィルタリング、検索（ページネーション対応） |
| **Dream Log** | バックグラウンド整理プロセスのリアルタイムログ |
| **Graph** | 記憶の接続を示す知識グラフの可視化 |

### 各タブの詳細

**Overview タブ**
- タイプ別の記憶数（Insights, Successes, Failures, Decisions, Notes）
- コンテキストとタグのクラウド（クリックでフィルタリング）
- 健全性スコアと改善提案

**Memories タブ**
- タイプでフィルター（Insight/Success/Failure/Decision/Note）
- コンテキスト（プロジェクト）でフィルター
- クリックで詳細とリンクを表示

**Graph タブ**
- インタラクティブなノード可視化
- 記憶タイプ別の色分け：
  - 🔵 シアン: Insights
  - 🟠 オレンジ: Decisions
  - 🟢 緑: Successes
  - 🔴 赤: Failures
- 線は `RELATED_TO` 接続を表示

### スタンドアロンダッシュボードモード

別のポートでダッシュボードだけを起動することも可能：

```bash
uv run exocortex --mode dashboard --dashboard-port 8766
```

> **Note:** スタンドアロンモードでは、ダッシュボードは同じデータベースに接続しますが、MCPサーバーは含まれません。

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
