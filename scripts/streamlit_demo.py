"""
CodeLitmus UIプロトタイプ — Streamlitで実現できる範囲のデモ

管理番号5-5の必須条件:
 1. LLMから投げられた質問を表示すること
 2. 必要に応じて図が使えて回答を文字で入力できること
 3. その入力が表示されること

このデモではLLMは使わず、ダミーデータで「UIとしてどこまでできるか」を確認する。
"""
import streamlit as st
import time

# ページ設定
st.set_page_config(
    page_title="CodeLitmus — コード理解サポート",
    page_icon="🧠",
    layout="wide",
)

# ─────────────────────────────────────
# ダミーデータ（本番ではLLM + AST）
# ─────────────────────────────────────
DEMO_CODE = '''def validate_input(user_data: dict) -> tuple[bool, str]:
    if "name" not in user_data:
        return False, "名前は必須です"
    if len(user_data["name"]) > 100:
        return False, "名前は100文字以内です"
    return True, ""

def process_data(raw: list[dict]) -> list[dict]:
    validated = []
    for item in raw:
        ok, msg = validate_input(item)
        if ok:
            validated.append(item)
    return validated'''

DEMO_CHUNKS = [
    {
        "name": "validate_input",
        "type": "function",
        "lines": "1-6",
        "args": ["user_data: dict"],
        "returns": "tuple[bool, str]",
    },
    {
        "name": "process_data",
        "type": "function",
        "lines": "8-14",
        "args": ["raw: list[dict]"],
        "returns": "list[dict]",
    },
]

DEMO_QUESTION = {
    "text": "`validate_input()` 関数は、引数 `user_data` に対してどのようなバリデーションを行い、どんな値を返すか説明してください。",
    "axis": "構造軸（物理的内容）",
    "mermaid": """```mermaid
graph TD
    A["validate_input(user_data)"] --> B{"'name' in user_data?"}
    B -->|No| C["return False, 'エラー'"]
    B -->|Yes| D{"len > 100?"}
    D -->|Yes| E["return False, 'エラー'"]
    D -->|No| F["return True, ''"]
```""",
}

DEMO_SCORING = {
    "score": 75,
    "feedback": "関数の目的（バリデーション）は正しく説明できています。ただし、戻り値が `tuple[bool, str]` であることと、2つのバリデーション条件（nameキーの存在チェック、文字数チェック）の順序についての説明が不足しています。",
    "details": [
        {"item": "関数の目的", "score": 20, "max": 20, "comment": "✅ 正確"},
        {"item": "引数の説明", "score": 15, "max": 20, "comment": "△ 型の記述が不足"},
        {"item": "戻り値の説明", "score": 10, "max": 20, "comment": "△ tupleであることが未記述"},
        {"item": "処理の順序", "score": 15, "max": 20, "comment": "△ 2段階チェックの説明不足"},
        {"item": "呼び出し関係", "score": 15, "max": 20, "comment": "✅ 正確"},
    ],
}

# ─────────────────────────────────────
# セッション状態の管理
# ─────────────────────────────────────
if "step" not in st.session_state:
    st.session_state.step = "select"  # select → question → answered → scored
if "user_answer" not in st.session_state:
    st.session_state.user_answer = ""
if "target_score" not in st.session_state:
    st.session_state.target_score = 70
if "history" not in st.session_state:
    st.session_state.history = []

# ─────────────────────────────────────
# サイドバー
# ─────────────────────────────────────
with st.sidebar:
    st.title("🧠 CodeLitmus")
    st.caption("コード理解サポートエージェント")
    st.divider()

    # ① ファイル選択
    st.subheader("📁 対象ファイル")
    file_path = st.text_input(
        "ファイルパス",
        value="app/validator.py",
        help="理解したいファイルのパスを入力",
    )

    # ② 合格基準点
    st.subheader("🎯 合格基準点")
    st.session_state.target_score = st.slider(
        "基準点",
        min_value=10,
        max_value=100,
        value=st.session_state.target_score,
        step=10,
    )

    st.divider()

    # 進捗表示
    st.subheader("📊 進捗")
    progress = 0
    if st.session_state.step == "scored":
        progress = 50
    st.progress(progress / 100)
    st.caption(f"Chunk: {progress // 50}/2 完了")

    st.divider()

    # 中断ボタン
    if st.button("⏹️ 中断する", use_container_width=True):
        st.session_state.step = "select"
        st.session_state.user_answer = ""
        st.rerun()

    # 履歴表示
    if st.session_state.history:
        st.subheader("📜 履歴")
        for h in st.session_state.history:
            emoji = "✅" if h["passed"] else "❌"
            st.caption(f"{emoji} {h['chunk']} — {h['score']}点")

# ─────────────────────────────────────
# メインエリア
# ─────────────────────────────────────

# ステップ: ファイル選択 → 開始
if st.session_state.step == "select":
    st.title("🧠 コード理解テスト")
    st.info(f"📁 対象: `{file_path}`　|　🎯 合格基準: {st.session_state.target_score}点")

    # コードプレビュー
    st.subheader("対象コード")
    st.code(DEMO_CODE, language="python", line_numbers=True)

    # Chunk一覧
    st.subheader("Chunk一覧（AST解析結果）")
    cols = st.columns(len(DEMO_CHUNKS))
    for i, chunk in enumerate(DEMO_CHUNKS):
        with cols[i]:
            st.metric(
                label=f"Chunk {i+1}",
                value=chunk["name"],
                delta=f"{chunk['type']} | 行 {chunk['lines']}",
            )

    if st.button("▶️ テスト開始", type="primary", use_container_width=True):
        st.session_state.step = "question"
        st.rerun()

# ステップ: 質問表示 + 回答入力
elif st.session_state.step == "question":
    st.title("📝 質問")

    # 質問のメタ情報
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"**Chunk 1 / 2** — `validate_input()`")
    with col2:
        st.metric("軸", DEMO_QUESTION["axis"])

    # ★ 必須条件1: 質問を表示
    st.markdown(f"### {DEMO_QUESTION['text']}")

    # ★ 必須条件2: 図の表示（Mermaid）
    with st.expander("📊 参考図（Mermaid）", expanded=True):
        st.markdown(DEMO_QUESTION["mermaid"])

    # 元コードの参照（折りたたみ）
    with st.expander("🔍 対象コードを確認"):
        st.code(DEMO_CODE.split("\n\n")[0], language="python", line_numbers=True)

    st.divider()

    # ★ 必須条件2: 回答入力
    st.subheader("✏️ あなたの回答")
    answer = st.text_area(
        "回答を入力してください",
        height=200,
        placeholder="この関数は...",
        key="answer_input",
    )

    col_submit, col_skip = st.columns([3, 1])
    with col_submit:
        if st.button("📤 回答を提出", type="primary", use_container_width=True, disabled=not answer):
            st.session_state.user_answer = answer
            st.session_state.step = "answered"
            st.rerun()
    with col_skip:
        if st.button("⏭️ スキップ", use_container_width=True):
            st.session_state.user_answer = "(スキップ)"
            st.session_state.step = "answered"
            st.rerun()

# ステップ: 採点中（アニメーション）→ 結果表示
elif st.session_state.step == "answered":
    st.title("⏳ 採点中...")
    progress_bar = st.progress(0)
    for i in range(100):
        time.sleep(0.01)
        progress_bar.progress(i + 1)
    st.session_state.step = "scored"
    st.rerun()

# ステップ: 採点結果
elif st.session_state.step == "scored":
    st.title("📊 採点結果")

    score = DEMO_SCORING["score"]
    passed = score >= st.session_state.target_score

    # スコア表示
    col_score, col_judge = st.columns([1, 1])
    with col_score:
        st.metric(
            "スコア",
            f"{score} / 100",
            delta=f"基準 {st.session_state.target_score}点",
        )
    with col_judge:
        if passed:
            st.success("## ✅ 合格", icon="🎉")
        else:
            st.error("## ❌ 不合格", icon="📖")

    st.divider()

    # ★ 必須条件3: 入力内容の表示
    st.subheader("✏️ あなたの回答")
    st.markdown(f"> {st.session_state.user_answer}")

    st.divider()

    # フィードバック
    st.subheader("💬 フィードバック")
    st.warning(DEMO_SCORING["feedback"])

    # 項目別スコア
    st.subheader("📋 項目別スコア")
    for detail in DEMO_SCORING["details"]:
        col_name, col_bar, col_comment = st.columns([2, 3, 3])
        with col_name:
            st.write(f"**{detail['item']}**")
        with col_bar:
            st.progress(detail["score"] / detail["max"])
            st.caption(f"{detail['score']} / {detail['max']}")
        with col_comment:
            st.caption(detail["comment"])

    st.divider()

    # 履歴に追加
    if not any(h["chunk"] == "validate_input" for h in st.session_state.history):
        st.session_state.history.append({
            "chunk": "validate_input",
            "score": score,
            "passed": passed,
        })

    # 次のアクション
    col_next, col_retry = st.columns(2)
    with col_next:
        if st.button("▶️ 次のChunkへ", type="primary", use_container_width=True):
            st.session_state.step = "question"
            st.session_state.user_answer = ""
            st.rerun()
    with col_retry:
        if st.button("🔄 もう一度回答する", use_container_width=True):
            st.session_state.step = "question"
            st.session_state.user_answer = ""
            st.rerun()
