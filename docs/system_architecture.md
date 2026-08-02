# コード理解サポートエージェント — システム全体構成図

> **ドキュメントバージョン**: v1.0（2026-08-02）
> **原典**: `20260801_コード理解サポートエージェント_検討整理 - シート1.pdf`

---

## 1. システム概要

バイブコーディングによって発生する **「理解負債」** を、能動学習（アクティブラーニング）とテストによって解消・測定・管理するシステム。

```mermaid
graph LR
    A["理解負債の発生"] --> B["本システム"]
    B --> C["能動学習・テスト"]
    C --> D["理解度の測定・管理"]
    D --> E["理解負債の解消"]
```

> [!IMPORTANT]
> コード理解の「解説」ではなく、**質問→回答→採点→フィードバック** のサイクルによる能動学習に特化する（管理番号9, 9-1）

---

## 2. 全体アーキテクチャ（3層構成）

```mermaid
graph TD
    subgraph UI ["① UI層 — Streamlit"]
        UI_FileSelect["ファイル/フォルダ選択"]
        UI_ScoreSetting["合格基準点の設定"]
        UI_QuestionView["質問表示 + Mermaid図"]
        UI_AnswerInput["ユーザー回答入力<br/>（文章）"]
        UI_Feedback["採点結果 + フィードバック表示"]
        UI_Interrupt["中断ボタン"]
        UI_History["学習履歴・進捗表示"]
    end

    subgraph Core ["② ロジック層 — Python"]
        CodeParser["ソースコード解析<br/>Chunk分割（関数/クラス単位）"]
        SessionCtrl["セッション管理<br/>（進行・中断・再開）"]

        subgraph LLM_Tasks ["LLMタスク管理"]
            PromptQ["質問生成プロンプト<br/>・論理的内容（処理の塊）<br/>・物理的内容（関数・引数）<br/>・Few-Shot例 2-3パターン"]
            PromptEval["採点評価プロンプト<br/>・回答の正確性判定<br/>・スコアリング<br/>・Few-Shot例 2-3パターン"]
        end

        ScoreJudge["合否判定ロジック<br/>（設定点数 vs 採点結果）"]
        MermaidGen["Mermaid図変換"]
    end

    subgraph Data ["③ データ層 — ローカルDB（SQLite）"]
        DB[(SQLite)]
        T_Projects["projects テーブル<br/>ファイルパス参照・全体進捗"]
        T_Sessions["sessions テーブル<br/>目標点数・ステータス"]
        T_QA["qa_histories テーブル<br/>質問・回答・スコア・FB"]
    end

    %% UI → Core
    UI_FileSelect -->|"1. 対象パス指定"| CodeParser
    UI_ScoreSetting -->|"2. 合格基準点"| SessionCtrl
    UI_AnswerInput -->|"4. ユーザー回答"| SessionCtrl
    UI_Interrupt -->|"中断シグナル"| SessionCtrl

    %% Core内部
    CodeParser -->|"コードChunk"| SessionCtrl
    SessionCtrl -->|"3. 質問生成依頼"| PromptQ
    SessionCtrl -->|"5. 採点依頼"| PromptEval
    PromptEval -->|"採点結果"| ScoreJudge
    PromptQ -->|"コード→図"| MermaidGen

    %% Core → UI
    PromptQ -->|"質問テキスト"| UI_QuestionView
    MermaidGen -->|"Mermaid図"| UI_QuestionView
    ScoreJudge -->|"6. 採点FB + 合否"| UI_Feedback
    ScoreJudge -->|"不合格→再テスト"| SessionCtrl

    %% Core → Data
    SessionCtrl <-->|"履歴読み書き"| DB
    DB --- T_Projects
    DB --- T_Sessions
    DB --- T_QA
```

---

## 3. 操作フロー（ユーザーシーケンス）

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant UI as Streamlit UI
    participant Core as ロジック層
    participant LLM as LLM（1つ）
    participant DB as SQLite

    User->>UI: ① ファイル/フォルダを選択
    User->>UI: ② 合格基準点を設定
    UI->>Core: 対象パス + 基準点
    Core->>Core: ソースコード読み込み & Chunk分割

    loop 全Chunkカバー or ユーザー中断まで
        Core->>LLM: ③ 質問生成プロンプト（Chunk付き）
        LLM-->>Core: 質問テキスト + Mermaid図
        Core-->>UI: 質問 + 図を表示

        User->>UI: ④ 回答を入力（文章）
        UI->>Core: 回答テキスト

        Core->>LLM: ⑤ 採点評価プロンプト（質問 + 回答 + コード）
        LLM-->>Core: スコア + フィードバック

        Core->>DB: 質問・回答・スコア・FBを保存

        alt スコア >= 基準点
            Core-->>UI: ⑥ 合格表示 → 次のChunkへ
        else スコア < 基準点
            Core-->>UI: ⑥ 不合格表示 + FB → 再回答を促す
        end
    end

    Core-->>UI: ⑦ 完了 or 中断状態を表示
    Core->>DB: セッション状態を保存
```

---

## 4. データモデル（ER図）

```mermaid
erDiagram
    projects ||--o{ sessions : "has"
    sessions ||--o{ qa_histories : "contains"

    projects {
        int id PK
        string file_path "対象ファイル/フォルダのパス参照"
        float overall_score "全体理解度スコア"
        datetime created_at
        datetime updated_at
    }

    sessions {
        int id PK
        int project_id FK
        int target_score "合格基準点"
        string status "進行中/完了/中断"
        datetime started_at
        datetime ended_at
    }

    qa_histories {
        int id PK
        int session_id FK
        string chunk_ref "対象Chunk識別子"
        string question_type "論理的/物理的"
        text question "LLM生成の質問"
        text mermaid_diagram "Mermaid図（nullable）"
        text user_answer "ユーザー回答"
        int score "採点スコア"
        text feedback "LLMフィードバック"
        boolean is_passed "合否"
        datetime answered_at
    }
```

> [!NOTE]
> ソースコード本体はDBに保存しない。**パス参照**に留め、質問・回答・スコアの履歴のみを永続化する（管理番号8-1）

---

## 5. LLMプロンプト構成

```mermaid
graph TD
    subgraph SingleLLM ["LLM（1つ）"]
        subgraph QPrompt ["質問生成プロンプト"]
            QSystem["System: あなたはコードの理解度を<br/>テストする試験官です"]
            QFewShot["Few-Shot例（2-3パターン）<br/>・論理的な質問例<br/>・物理的な質問例"]
            QInput["User: 対象コードChunk"]
            QOutput["Output: 質問テキスト + Mermaid図"]
        end
        subgraph EPrompt ["採点評価プロンプト"]
            ESystem["System: あなたは回答を採点する<br/>評価者です"]
            EFewShot["Few-Shot例（2-3パターン）<br/>・良い回答 → 高スコア<br/>・不十分な回答 → 低スコア"]
            EInput["User: 質問 + 回答 + 元コード"]
            EOutput["Output: スコア + フィードバック"]
        end
    end
```

---

## 6. 開発ロードマップ

```mermaid
graph LR
    P1["Phase 1<br/>Streamlit MVP<br/>（プロトタイプ）"]
    P2["Phase 2<br/>品質向上<br/>（プロンプト最適化・UI改善）"]
    P3["Phase 3<br/>VS Code拡張機能<br/>（実用版）"]

    P1 -->|"実用性判断"| P2
    P2 -->|"耐えうると判断"| P3

    style P1 fill:#4CAF50,color:#fff
    style P2 fill:#FF9800,color:#fff
    style P3 fill:#2196F3,color:#fff
```

| Phase | 形態 | 主な内容 |
|:---:|:---|:---|
| 1 | Streamlit（Python） | 最小ループ動作確認：1ファイル → 質問 → 回答 → 採点 |
| 2 | Streamlit（改善版） | プロンプトFew-Shot最適化、履歴表示、複数ファイル対応 |
| 3 | VS Code 拡張機能 | 開発フローとの統合、利用タイミングのモード分離（管理番号9-2） |

---

## 7. 技術スタック一覧

| レイヤー | 技術 | 備考 |
|:---|:---|:---|
| UI | Streamlit → VS Code Extension | Phase 1はStreamlit、Phase 3でVS Code |
| ロジック | Python | コード解析・セッション管理・プロンプト構築 |
| LLM | ローカルLLM（Ollama等） | API（Claude/OpenAI）も選択肢（管理番号5-1） |
| データ | SQLite | ローカルDB。パス参照方式（管理番号8-1） |
| 図表現 | Mermaid | プログラムをMermaid図に変換して表示（管理番号1-2-1） |

---

## 8. 差別化ポイント

```mermaid
mindmap
  root["コード理解サポートエージェント"]
    既存ツールとの違い
      解説・補完ではない
      能動学習・テスト特化
    コア機能
      質問生成（論理/物理）
      回答採点・フィードバック
      理解度トラッキング
    価値提供
      理解負債の防止
      理解負債の測定
      理解負債の管理
```
