# DeDoubt データコントラクト — Chunkオブジェクトのスキーマ

> このドキュメントは Python解析層(`dedoubt/parser.py`, `dedoubt/core.py`)・HTTP API層(`main.py`)・
> VS Code拡張ホスト(`vscode-extension/src/extension.ts`)・Webviewレンダラー(`vscode-extension/src/webview/index.html`)
> を実装コードから直接読み、境界を越えるたびにデータがどう変わるかをまとめたものです。

## 0. 最初に: 実際のデータフローは「解析→拡張ホスト→描画」ではない

想定されがちな流れ（Python解析 → 拡張機能ホスト → Webview描画）とは異なり、実際は次の通りです。

```
dedoubt/parser.py (AST解析)
   └─ CodeChunk オブジェクト
        └─ dedoubt/core.py が dict化してセッション情報に同梱
             └─ main.py (vscode-extension/配下, FastAPI, http://127.0.0.1:8000)
                  └─ Webview (index.html) が fetch() で直接HTTPを叩く
                       └─ 星座マップ・質問・採点結果を描画

vscode-extension/src/extension.ts
        └─ Webviewへ postMessage する内容は { filePath, targetScore } の切り替え通知のみ
           （Chunkデータそのものは一切経由しない）
```

**拡張機能ホスト(`extension.ts`)はChunk/セッション/スコアのデータを中継していません。** Webviewはアクティブファイルが切り替わったことだけを拡張ホストから知らされ、そのあとは自分でFastAPIサーバーに直接HTTPリクエストを投げてすべてのデータを取得します。

FastAPIアプリの実体は[`main.py`](../vscode-extension/main.py)(`vscode-extension/main.py`)で、`python main.py`で起動する。`dedoubt/`パッケージもmain.pyと同じ`vscode-extension/`配下に同居させている(2026-08-09に移動)。理由: `vsce package`(拡張機能の配布パッケージ作成)は`vscode-extension/`配下しか対象にしないため、Pythonバックエンドをこの外に置いたままでは配布物に含まれない。

> 過去には`server/`ディレクトリ(`server_app.py`, `run_server.py`, `server/run.py`, `server/test_server.py`)が存在し、いずれも存在しない`server/main.py`を`from server.main import app` / `from main import app`でインポートしようとする死んだコードだった(実行すると全て`ModuleNotFoundError`)。おそらく`main.py`を`server/`配下へ移す途中で放棄されたリファクタリングの残骸。2026-08-09に削除済み。

---

## 1. CodeChunk — 解析結果の中核オブジェクト

出典: [`dedoubt/parser.py`](../vscode-extension/dedoubt/parser.py) の `CodeChunk` dataclass（`to_dict()`でこの形のdictになる）。

```json
{
  "name": "string",
  "chunk_type": "function | class | entrypoint",
  "start_line": "int (1-based)",
  "end_line": "int (1-based, inclusive)",
  "code_segment": "string — 該当行のソースコードそのまま",
  "args": ["string", "..."],
  "docstring": "string または null",
  "methods": ["string", "..."] または null,
  "calls": ["string", "..."]
}
```

| フィールド | 必須/オプション | 補足 |
|---|---|---|
| `name` | 必須 | 関数名・クラス名。entrypointの場合は `"__main__"`（`if __name__ == "__main__":` ガードのみのとき）または `"モジュールの実行フロー"`（それ以外のトップレベル文がある場合）。**ファイル内で高々1つ**。 |
| `chunk_type` | 必須 | `"function"` \| `"class"` \| `"entrypoint"` の3値のみ。 |
| `args` | 必須（配列は常に存在） | `function`のみ実引数名が入る。`class`/`entrypoint`は常に`[]`。 |
| `docstring` | オプション（既定`null`） | `function`/`class`のみ。`entrypoint`は常に`null`。 |
| `methods` | オプション（既定`null`） | `class`のみメソッド名一覧。`function`/`entrypoint`は`null`（`[]`ではない点に注意）。 |
| `calls` | 必須（配列は常に存在、既定`[]`） | このChunkのトップレベルコードから**直接呼び出している**他Chunk名（`foo()`形式のみ検出。`obj.method()`のような属性呼び出しは対象外）。自己再帰は除外。2パス目で全Chunk名確定後に解決するため定義順に依存しない。 |

**スコアはここでは計算されない。** CodeChunkはAST解析結果のみを保持し、採点は境界3（`/api/answer/evaluate`）でのみ発生する。

---

## 2. 境界①: Python解析層 → セッション初期化レスポンス

出典: [`dedoubt/core.py`](../vscode-extension/dedoubt/core.py) `DeDoubtCore.start_session_for_file()`。

```json
{
  "project": {
    "id": "int",
    "file_path": "string",
    "file_hash": "string (SHA256)",
    "overall_score": "float",
    "created_at": "string (ISO8601)",
    "updated_at": "string (ISO8601)"
  },
  "session": {
    "id": "int",
    "project_id": "int",
    "target_score": "int",
    "status": "in_progress | completed | interrupted",
    "started_at": "string (ISO8601)",
    "ended_at": "string (ISO8601) または null"
  },
  "chunks": ["CodeChunk dict の配列（§1参照）"],
  "current_chunk_index": 0
}
```

`project`/`session`のフィールドは [`dedoubt/db.py`](../vscode-extension/dedoubt/db.py) の `projects`/`sessions` テーブル定義そのまま（SQLite行を`dict()`化したもの）。

---

## 3. 境界②: FastAPI サーバー (`vscode-extension/main.py`)

Webview (`index.html`) 内の `API_BASE = "http://127.0.0.1:8000"` への `fetch()` 呼び出しを起点に整理。実装は[`main.py`](../vscode-extension/main.py)。

エラー時は`{"status":"error", ...}`ではなく、FastAPIの`HTTPException`による標準エラーボディ`{"detail": "string"}`（HTTP 404または500）を返す。Webview側は`json.status === 'success'`でしか分岐していないため、これでも「失敗」判定は正しく効くが、エラーメッセージ自体(`detail`)は現在どこにも表示されずトースト文言に固定されている。

`main.py`には`GET /api/dashboard/{session_id}`（セッションのQA履歴全件取得）も存在するが、現行のWebviewはこれを呼んでいない未使用エンドポイント。

### `GET /api/health`
Webviewが実際に読むのは `data.engine`（例: `"Ollama (Local LLM)"` / `"Mock Engine (Demo Mode)"`）のみ。実際のレスポンスには`status: "ok"`と`db_path`も含まれるが、Webviewはこの2つを読んでいない。

### `POST /api/session/start`
- リクエスト: `{ "file_path": "string", "target_score": "int" }`
- レスポンス: `{ "status": "success", "data": <§2のセッション初期化レスポンス> }`

### `POST /api/question/generate`
- リクエスト: `{ "chunk": <CodeChunk dict>, "axis": "構造軸 | 関係軸", "difficulty": "基礎 | 標準 | 応用" }`
- レスポンス:
```json
{
  "status": "success",
  "data": {
    "question": "string",
    "axis": "string",
    "difficulty": "string",
    "rubric": [{ "name": "string", "max": "int" }],
    "mermaid_diagram": "string または null"
  }
}
```
`rubric`の`max`合計は常に100になる想定（[`dedoubt/llm.py`](../vscode-extension/dedoubt/llm.py) `build_question_prompt`のプロンプト制約）。

### `POST /api/answer/evaluate`
- リクエスト: `{ "session_id": "int", "chunk": <CodeChunk dict>, "question_data": <question/generateのdata>, "user_answer": "string", "target_score": "int" }`
- レスポンス:
```json
{
  "status": "success",
  "data": {
    "qa_id": "int",
    "score": "int (0-100)",
    "is_passed": "bool",
    "score_details": [
      { "name": "string", "score": "int", "max": "int", "reason": "string" }
    ],
    "miss_categories": ["string", "..."],
    "feedback": "string",
    "history_summary": [
      { "score": "int", "is_passed": "bool", "answered_at": "string (ISO8601)" }
    ]
  }
}
```

**スコアはここで計算される**（[`dedoubt/core.py`](../vscode-extension/dedoubt/core.py) `evaluate_answer_and_save`）: `score_details`が返ってきた場合はサーバー側で各項目の`score`を合算して`score`を再計算する（LLMが返した`score`トップレベル値は`score_details`が空のときのフォールバックとしてのみ使う）。「わからない」等の無解回答は`is_unknown_or_empty_answer()`により即座に全項目0点。

### `GET /api/analytics/{project_id}`
```json
{
  "status": "success",
  "analytics": {
    "project_id": "int",
    "chunk_summary": {
      "<chunk name>": {
        "latest_score": "int",
        "max_score": "int",
        "attempts": "int",
        "last_passed": "bool",
        "last_feedback": "string"
      }
    },
    "top_weaknesses": [{ "category": "string", "count": "int" }]
  }
}
```

> ⚠ **envelopeの不整合**: 他の3エンドポイントはペイロードを`data`キーに入れるが、このエンドポイントだけ`analytics`キーを使う（Webview側`index.html`のコードでも`json.analytics`として読んでいる — `json.data`ではない）。新規エンドポイントを追加する際はこの不整合を広げないよう`data`に統一することを推奨。

---

## 4. 境界③: 拡張ホスト ⇔ Webview（VS Code postMessage）

出典: [`vscode-extension/src/extension.ts`](../vscode-extension/src/extension.ts), [`index.html`](../vscode-extension/src/webview/index.html) の `window.addEventListener('message', ...)`。

**Chunk/セッション/スコアはここを一切通らない。** やり取りされるのはファイル切り替え通知のみ。

ホスト → Webview:
```json
{ "command": "initSession | switchFile", "filePath": "string", "targetScore": "int" }
```

Webview → ホスト:
```json
{ "command": "ready" }
```

（`ready`は起動直後のハンドシェイク用。ホストは`isReady`になるまでメッセージをキューイングする。）

---

## 5. 全体まとめ表

| データ | 生成場所 | 保存場所 | 消費場所 |
|---|---|---|---|
| `CodeChunk`（§1） | `dedoubt/parser.py` | セッション中はメモリのみ（DB非永続化） | Webview（星座マップ描画・質問/採点APIへのリクエスト同梱） |
| `question.rubric` / `mermaid_diagram` | LLM（Ollama/Mock, `dedoubt/llm.py`） | `qa_histories.mermaid_diagram`（DB） | Webview（質問表示・図解モーダル） |
| `score` / `score_details` / `miss_categories` | `dedoubt/core.py`（LLM出力をサーバー側で再計算） | `qa_histories`（DB, JSON文字列） | Webview（採点結果表示・星座マップの合否色分け） |
| `chunk_summary` / `top_weaknesses` | `dedoubt/db.py` `get_project_analytics()` | 集計元は`qa_histories` | Webview（星座マップの既学習ステータス、終了画面） |

---

## 6. 「デモ固有ロジック禁止」ルールとの関係

[`CLAUDE.md`](../CLAUDE.md) の「No Demo-Specific Logic」ルールは、この契約があることで機械的にチェックしやすくなる。例えば `MockLLMClient.ask()`（[`dedoubt/llm.py`](../vscode-extension/dedoubt/llm.py)）は `"名前: __main__"` や `"名前: divide_with_raise"` のようにプロンプト文字列へ特定のChunk名が含まれるかで分岐しているが、これは**デモ用フォールバック実装として明示されている**ものであり、本番の採点経路（Ollama接続時）はこの分岐を通らない。新しいスコアリングロジックを実装する際は、`MockLLMClient`ではなく`OllamaClient`経路、または本ドキュメントのスキーマに対するプロパティベーステストで検証すること。
