# コード理解サポートエージェント — システム全体構成図

> **ドキュメントバージョン**: v1.1（2026-08-05）  
> **原典**: `20260801_コード理解サポートエージェント_検討整理 - シート1 (2).csv`

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
        UI_ModeSelect["学習モード選択<br/>（ざっくり/しっかり/弱点克服）"]
        UI_QuestionView["質問表示 + Mermaid図"]
        UI_AnswerInput["ユーザー回答入力<br/>（文章）"]
        UI_Feedback["採点結果 + フィードバック表示<br/>（項目別スコア・理由）"]
        UI_Interrupt["中断ボタン"]
        UI_History["学習履歴・進捗表示"]
    end

    subgraph Core ["② ロジック層 — Python"]
        CodeParser["AST解析 (astモジュール)<br/>Chunk分割（関数/クラス単位）"]
        SessionCtrl["セッション管理<br/>（進行・中断・再開）"]

        subgraph LLM_Client ["LLM抽象化層 (LLMClient)"]
            OllamaClient["OllamaClient (Phase 1)"]
            ClaudeClient["Claude/OpenAI (将来用)"]
        end

        subgraph LLM_Tasks ["LLMタスク管理"]
            PromptQ["質問生成プロンプト<br/>・構造軸/関係軸/難易度<br/>・Few-Shot例"]
            PromptEval["採点評価プロンプト<br/>・項目別判定+理由<br/>・ミスタグ抽出"]
        end

        ScoreJudge["合否判定ロジック<br/>（設定点数 vs 採点結果）"]
        MermaidGen["Mermaid図変換"]
    end

    subgraph Data ["③ データ層 — ローカルDB（SQLite）"]
        DB[(SQLite)]
        T_Projects["projects テーブル<br/>ファイルパス参照・hash・全体進捗"]
        T_Sessions["sessions テーブル<br/>目標点数・ステータス"]
        T_QA["qa_histories テーブル<br/>質問・回答・スコア詳細・ミスタグ・難易度"]
    end

    %% UI → Core
    UI_FileSelect -->|"1. 対象パス指定"| CodeParser
    UI_ScoreSetting -->|"2. 合格基準点"| SessionCtrl
    UI_ModeSelect -->|"プロンプト条件設定"| SessionCtrl
    UI_AnswerInput -->|"4. ユーザー回答"| SessionCtrl
    UI_Interrupt -->|"中断シグナル"| SessionCtrl

    %% Core内部
    CodeParser -->|"コードChunk"| SessionCtrl
    SessionCtrl -->|"3. 質問生成依頼"| LLM_Client
    SessionCtrl -->|"5. 採点依頼"| LLM_Client
    LLM_Client --> PromptQ
    LLM_Client --> PromptEval
    PromptEval -->|"採点結果(JSON)"| ScoreJudge
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
    participant LLM as LLM (Ollama)
    participant DB as SQLite

    User->>UI: ① ファイル/フォルダを選択
    User->>UI: ② 合格基準点・モードを設定
    UI->>Core: 対象パス + 基準点 + モード
    Core->>Core: ソースコード読み込み & AST Chunk分割

    loop 全Chunkカバー or ユーザー中断まで
        Core->>LLM: ③ 質問生成プロンプト（Chunk + 難易度）
        LLM-->>Core: 質問テキスト + Mermaid図
        Core-->>UI: 質問 + 図を表示

        User->>UI: ④ 回答を入力（文章）
        UI->>Core: 回答テキスト

        Core->>LLM: ⑤ 採点評価プロンプト（質問 + 回答 + コード）
        LLM-->>Core: スコア + 理由(JSON) + ミスタグ
        Core->>DB: 質問・回答・スコア詳細・FBを保存

        alt スコア >= 基準点
            Core-->>UI: ⑥ 合格表示 → 次のChunkへ
        else スコア < 基準点
            Core-->>UI: ⑥ 不合格表示 + 理由FB → 再回答を促す
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
        string file_hash "ファイルのハッシュ値（変更検知用）"
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
        string difficulty "質問の難易度（基礎/標準/応用）"
        text question "LLM生成の質問"
        text mermaid_diagram "Mermaid図（nullable）"
        text user_answer "ユーザー回答"
        int score "採点スコア"
        text score_details "項目別スコアと理由（JSON）"
        text miss_categories "ミスの分類タグ（JSON配列）"
        text feedback "LLMフィードバック"
        boolean is_passed "合否"
        datetime answered_at
    }
```

> [!NOTE]
> ソースコード本体はDBに保存せず**パス参照**に留め、質問・回答・スコアの履歴のみを永続化する（管理番号8-1）。
> 
> **追加設計項目**（検討番号3-2-1-3, 3-2-1-3-2, 3-2-1-3-3）:
> - `file_hash`: ファイル変更検知。前回テスト時と内容が変わったか判定する
> - `score_details`: 項目別スコア+理由のJSON。「どこで間違えたか」を透明化する
> - `miss_categories`: ミス分類タグ。「考え方の癖」を将来分析・蓄積する
> - `difficulty`: 質問の難易度。段階的エスカレーションや弱点克服モードに使用する

---

## 5. LLM接続の抽象化（管理番号5-1-1）

```python
class LLMClient:
    """LLM通信を抽象化するインタフェース"""
    def ask(self, prompt: str) -> str:
        raise NotImplementedError

class OllamaClient(LLMClient):
    """Phase 1で採用するローカルLLM用クライアント"""
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def ask(self, prompt: str) -> str:
        # Ollama API 呼び出し (temperature=0推奨)
        ...
```

> **方針**: Phase 1はOllamaのみ実装するが、`LLMClient` 抽象クラスを経由させることで、Phase 2以降のClaude / OpenAI APIへの差し替えコストを最小限に抑える。

---

## 6. 体験設計（UX）方針 3原則（管理番号4-2-1-1）

1. **具体的な変化を伝える**: 抽象的な褒め言葉ではなく「前回できなかった○○が今回できた」という客観的事実を伝える。
2. **間違えたら次の一手を示す**: 「不正解」で終わらせず「○○の記述に注目して再回答してください」と導く。
3. **ユーザーが自分で決められる**: テスト対象・基準点・モード・中断をユーザー自身の意思でコントロールさせる。

---

## 7. 開発ロードマップとPhase 1の完了判定（管理番号10-1）

```mermaid
graph LR
    P1["Phase 1<br/>Streamlit MVP<br/>（プロトタイプ）"]
    P2["Phase 2<br/>品質向上・ダッシュボード<br/>（プロンプト最適化・UI改善）"]
    P3["Phase 3<br/>VS Code拡張機能<br/>（実用版）"]

    P1 -->|"効果を実感"| P2
    P2 -->|"耐えうると判断"| P3

    style P1 fill:#4CAF50,color:#fff
    style P2 fill:#FF9800,color:#fff
    style P3 fill:#2196F3,color:#fff
```

### Phase 1 の目的
1つのPythonファイルを対象に、質問→回答→採点の最小ループを動かし、**「コード理解の深まり」を自分自身で体感できるか検証する**。

### Phase 1 完了判定4条件
1. LLMが的外れでない質問を生成できる
2. 採点とフィードバックの根拠（理由）が納得できる
3. 2回目の回答でスコアが上がる（学び直しループが動く）
4. 終了後に「このコードを説明できる」自信がつく

---

## 8. 技術スタック一覧

| レイヤー | 技術 | 備考 |
|:---|:---|:---|
| UI | Streamlit → VS Code Extension | Phase 1はStreamlit、Phase 3でVS Code |
| ロジック | Python (`ast` モジュール) | コード解析・Chunk分割・プロンプト構築 |
| LLM | ローカルLLM（Ollama等） | `LLMClient` 経由で呼び出し（管理番号5-1-1） |
| データ | SQLite | ローカルDB。パス参照方式（管理番号8-1） |
| 図表現 | Mermaid | プログラムをMermaid図に変換して表示（管理番号1-2-1） |
