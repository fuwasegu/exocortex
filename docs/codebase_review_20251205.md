# Exocortex Codebase Critical Review
Date: 2025-12-05
Target: `exocortex` repository

## 1. 総合評価 (Summary)

**ステータス: 良 (Good) だが、構成上の「要修正」事項あり**

Exocortex プロジェクトは、**Clean Architecture (DDD的構成)** を採用しており、責務の分離が意識された良質なコードベースです。ドメインロジック、インフラ、依存解決が綺麗に分離されており、テスト容易性が高い設計になっています。

しかし、**プロジェクト構成上の重大な混乱（ディレクトリの重複）** と、**将来的なスケーラビリティに関する実装上の懸念** が見つかりました。これらは早期に対処する必要があります。

---

## 2. プロジェクト構成 (Structure & Config)

### 🔴 Critical: ディレクトリ構成の二重管理
現在、ファイルシステム上に以下の2つのパッケージが存在し、競合状態にあります。

1.  **`src/exocortex/`**: Untracked (Git管理外)。おそらく古い構成の名残。
2.  **`exocortex/`**: Tracked (Git管理下)。現在アクティブに開発されているコード。

*   **現状**: `pyproject.toml` は `exocortex = "exocortex.main:main"` を指しており、ルート直下のパッケージが使われる設定です。一方で、`docs/design_doc.md` (Section 8) には `src/exocortex/` と記載されており、ドキュメントと実装、およびファイルシステムの状態が乖離しています。
*   **リスク**: 開発者が誤って `src/` 側を参照・修正してしまい、変更が反映されないといった混乱の原因になります。

---

## 3. アーキテクチャ & 設計 (Architecture & Design)

### ✅ Good: Clean Architecture / DDD構成
レイヤー分離が適切に行われています。

*   **Domain Layer** (`domain/`): 純粋なビジネスロジック。外部ライブラリへの依存が最小限。
*   **Infrastructure Layer** (`infra/`): KùzuDB や Embedding Engine などの具体的な技術実装。
*   **DI Container** (`container.py`): 依存性の注入を一元管理しており、結合度を低く保っています。

特に `MemoryService` が単なるCRUDラッパーではなく、しきい値判定や矛盾検知などの「ドメイン知識」を持っている点は高く評価できます。

### ⚠️ Warning: `MemoryRepository` の肥大化
`exocortex/infra/repositories.py` が 1000行を超えており、**God Class** 化の兆候があります。

*   **混在している責務**:
    *   データの永続化 (本来の責務)
    *   グラフ構造の構築ロジック
    *   テキスト処理（要約生成）
    *   データ分析（ナレッジベースの健全性診断）
    *   ベクトル計算（類似度計算）

### ⚠️ Warning: スケーラビリティの懸念 (O(N)処理)
新規記憶の保存時 (`store_memory`) に実行される分析処理 (`_analyze_new_memory`) にパフォーマンス上の懸念があります。

```python
# exocortex/domain/services.py
all_memories = self._repo.get_all_with_embeddings()
# ... Pythonループ内で全件と類似度計算 ...
```

*   **問題**: 既存の全記憶をメモリにロードし、Pythonプロセス内で全件比較を行っています。
*   **影響**: 記憶数が増加（数千件〜）すると、メモリ使用量とCPU処理時間が線形に増加し、レスポンスが悪化します。設計目標である「10,000件」の規模ではボトルネックとなる可能性が高いです。

---

## 4. 実装品質 (Code Quality)

*   **型安全性**: `mypy` に対応した型ヒントが全面的に適用されており、堅牢です。
*   **可読性**: Docstring が充実しており、各メソッドの意図が明確です。
*   **テスト**: `tests/` ディレクトリが整備され、`conftest.py` による環境リセットも実装されているため、テストの信頼性は高いです。

---

## 5. 推奨アクションプラン (Action Plan)

### Phase 1: クリーンアップ (Immediate)
混乱を避けるため、直ちに実施すべき項目です。
1.  **不要ディレクトリの削除**: `src/` ディレクトリを削除する。
2.  **ドキュメント修正**: `docs/design_doc.md` のディレクトリ構成図を現状（フラット構成）に合わせる。

### Phase 2: パフォーマンス改善 (High Priority)
実運用での遅延を防ぐための改修です。
1.  **ベクトル検索の委譲**: `store_memory` 時の類似検索を、Pythonループから KùzuDB のネイティブベクトル検索 (`CALL nn_search`) に切り替える。

### Phase 3: リファクタリング (Medium Priority)
保守性を高めるための改修です。
1.  **リポジトリの分割**: `MemoryRepository` から、「分析ロジック（Analyzer）」や「テキスト処理（Summarizer）」を別クラス/別モジュールに切り出す。


