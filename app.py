"""
DeDoubt — コード理解サポートエージェント (Streamlit アプリケーション)

Phase 1 実動MVPデモ
- 管理番号5-5の必須UI要件（質問表示、図サポート、文字入力と再表示）を完全実装
- 体験設計3原則（具体的な変化の伝達、次の一手提示、ユーザー選択主導）を統合
- ソクラテス的ヒント誘導（回答入力画面での前回のフィードバック & 着眼点ガイド表示）
"""
import streamlit as st
import streamlit.components.v1 as components
import os
import html
import re
from dedoubt.core import DeDoubtCore
from dedoubt.parser import CodeChunk
from dedoubt.llm import MockLLMClient, OllamaClient

def render_mermaid_diagram(mermaid_code: str, height: int = 280):
    """MermaidのテキストコードをHTML+Mermaid.js経由でSVGグラフィカル描画"""
    if not mermaid_code:
        return
    
    clean_code = mermaid_code.strip()
    if clean_code.startswith("```mermaid"):
        clean_code = clean_code.split("```mermaid")[1].split("```")[0].strip()
    elif clean_code.startswith("```"):
        clean_code = clean_code.split("```")[1].split("```")[0].strip()

    clean_code = re.sub(r'(\w+)\s*\[([^"\]]+)\]', r'\1["\2"]', clean_code)
    clean_code = re.sub(r'(\w+)\s*\{([^"\}]+)\}', r'\1["\2"]', clean_code)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
      <style>
        body {{
            background-color: #0e1117;
            color: #fafafa;
            font-family: sans-serif;
            margin: 0;
            padding: 10px;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: auto;
        }}
        .mermaid {{
            width: 100%;
            text-align: center;
        }}
      </style>
    </head>
    <body>
      <div class="mermaid">
{clean_code}
      </div>
      <script>
        document.addEventListener("DOMContentLoaded", function() {{
            try {{
                mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
            }} catch(e) {{
                console.error(e);
            }}
        }});
      </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=True)

# ページ基本設定
st.set_page_config(
    page_title="DeDoubt — コード理解サポートエージェント",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Coreインスタンスの初期化
if "core" not in st.session_state:
    try:
        client = OllamaClient()
        client.ask("connection test")
        st.session_state.core = DeDoubtCore(llm_client=client)
        st.session_state.engine_name = "Ollama (Local LLM)"
    except Exception:
        st.session_state.core = DeDoubtCore(llm_client=MockLLMClient())
        st.session_state.engine_name = "Mock Engine (Demo Mode)"

# セッション状態の初期化
if "step" not in st.session_state:
    st.session_state.step = "init"
if "target_score" not in st.session_state:
    st.session_state.target_score = 70
if "mode" not in st.session_state:
    st.session_state.mode = "しっかり"
if "session_data" not in st.session_state:
    st.session_state.session_data = None
if "current_chunk_idx" not in st.session_state:
    st.session_state.current_chunk_idx = 0
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "user_answer" not in st.session_state:
    st.session_state.user_answer = ""
if "eval_result" not in st.session_state:
    st.session_state.eval_result = None

DEFAULT_FILE_PATH = r"C:\Users\owner\Documents\lab\DeDoughtスプレッドシート\検証用ファイル\assert-and-raise.py"

# ──────────────────────────────────────────
# サイドバー
# ──────────────────────────────────────────
with st.sidebar:
    st.title("🧠 DeDoubt")
    st.caption("コード理解サポートエージェント (Phase 1 MVP)")
    st.caption(f"🤖 LLM Engine: `{st.session_state.engine_name}`")
    st.divider()

    st.subheader("📁 対象ファイル")
    file_path_input = st.text_input(
        "ローカルファイルパス",
        value=DEFAULT_FILE_PATH,
        help="理解を検証したいPythonファイルの絶対パスを入力"
    )

    st.subheader("🎯 合格基準点")
    st.session_state.target_score = st.slider(
        "合格目標スコア (点)",
        min_value=10,
        max_value=100,
        value=st.session_state.target_score,
        step=5
    )

    st.subheader("⚙️ 学習モード")
    st.session_state.mode = st.radio(
        "学習モード選択",
        ["ざっくり", "しっかり", "弱点克服"],
        index=1,
        help="ざっくり=物理概要 / しっかり=全観点 / 弱点克服=苦手抽出"
    )

    st.divider()

    if st.session_state.session_data:
        chunks = st.session_state.session_data["chunks"]
        total_chunks = len(chunks)
        current_idx = st.session_state.current_chunk_idx
        progress_val = min(1.0, current_idx / total_chunks) if total_chunks > 0 else 0
        st.subheader("📊 セッション進捗")
        st.progress(progress_val)
        st.caption(f"Chunk: {current_idx} / {total_chunks} カバー中")

    st.divider()

    if st.button("⏹️ セッション中断", use_container_width=True):
        if st.session_state.session_data:
            st.session_state.core.finish_session(
                st.session_state.session_data["session"]["id"],
                status="interrupted"
            )
        st.session_state.step = "init"
        st.session_state.session_data = None
        st.rerun()

# ──────────────────────────────────────────
# メインコンテンツ
# ──────────────────────────────────────────

# 【画面1: ファイル選択・準備画面】
if st.session_state.step == "init":
    st.title("🧠 コード理解テスト")
    st.markdown("バイブコーディングの **「理解負債」** を解消し、コードの構造と仕様を能動的に学習します。")
    st.info(f"📁 対象ファイル: `{file_path_input}` | 🎯 合格目標: **{st.session_state.target_score}点** | ⚙️ モード: **{st.session_state.mode}**")

    if os.path.exists(file_path_input):
        with open(file_path_input, "r", encoding="utf-8") as f:
            code_text = f.read()

        col_code, col_chunks = st.columns([3, 2])
        with col_code:
            st.subheader("ソースコード プレビュー")
            st.code(code_text, language="python", line_numbers=True)

        with col_chunks:
            st.subheader("AST解析 Chunk一覧")
            try:
                temp_session = st.session_state.core.start_session_for_file(file_path_input, st.session_state.target_score)
                chunks = temp_session["chunks"]
                st.success(f"✅ {len(chunks)} 個の Chunk（関数/クラス）を検出しました")
                
                for i, c in enumerate(chunks):
                    with st.container(border=True):
                        st.markdown(f"**Chunk {i+1}: `{c['name']}`**")
                        st.caption(f"種別: `{c['chunk_type']}` | 行: L{c['start_line']}-L{c['end_line']} | 引数: {c['args']}")

                st.divider()
                if st.button("▶️ テストセッション開始", type="primary", use_container_width=True):
                    st.session_state.session_data = temp_session
                    st.session_state.current_chunk_idx = 0
                    st.session_state.step = "generate_question"
                    st.rerun()

            except Exception as e:
                st.error(f"AST解析エラー: {e}")
    else:
        st.error(f"指定されたファイルが存在しません: `{file_path_input}`")

# 【画面2: 質問生成中】
elif st.session_state.step == "generate_question":
    st.title("📝 質問生成中...")
    chunks = st.session_state.session_data["chunks"]
    current_idx = st.session_state.current_chunk_idx

    if current_idx >= len(chunks):
        st.session_state.step = "finish"
        st.rerun()
    else:
        chunk_dict = chunks[current_idx]
        chunk_obj = CodeChunk(**chunk_dict)

        with st.spinner(f"Chunk `{chunk_obj.name}` の理解度測定質問を生成中..."):
            axis = "構造軸" if current_idx % 2 == 0 else "関係軸"
            difficulty = "標準"
            q_data = st.session_state.core.generate_question_for_chunk(
                chunk_obj,
                axis=axis,
                difficulty=difficulty,
                mode=st.session_state.mode
            )
            st.session_state.current_question = q_data
            st.session_state.user_answer = ""
            st.session_state.eval_result = None  # 新規Chunk用にリセット
            st.session_state.step = "question"
            st.rerun()

# 【画面3: 質問表示 & 回答入力画面】
elif st.session_state.step == "question":
    chunks = st.session_state.session_data["chunks"]
    current_idx = st.session_state.current_chunk_idx
    chunk_dict = chunks[current_idx]
    chunk_obj = CodeChunk(**chunk_dict)
    q_data = st.session_state.current_question

    st.title("📝 理解度チェック")

    col_meta1, col_meta2, col_meta3 = st.columns([2, 1, 1])
    with col_meta1:
        st.info(f"**Chunk {current_idx + 1} / {len(chunks)}** — `{chunk_obj.name}` ({chunk_obj.chunk_type})")
    with col_meta2:
        st.metric("理解軸", q_data.get("axis", "構造軸"))
    with col_meta3:
        st.metric("難易度", q_data.get("difficulty", "標準"))

    # 1. 質問テキスト
    st.markdown(f"### {q_data['question']}")

    # 2. Mermaid図の参考表示
    if q_data.get("mermaid_diagram"):
        with st.expander("📊 参考図 (Mermaid)", expanded=True):
            render_mermaid_diagram(q_data["mermaid_diagram"])

    # コード参照アコーディオン
    with st.expander(f"🔍 対象コードを確認 (`{chunk_obj.name}` L{chunk_obj.start_line}-L{chunk_obj.end_line})"):
        st.code(chunk_obj.code_segment, language="python", line_numbers=True)

    # ★【ユーザー提案に基づく改善】再挑戦時（2回目以降）に、回答入力画面で直前フィードバックと着眼点ガイドを直接表示！
    if st.session_state.eval_result and not st.session_state.eval_result.get("is_passed", False):
        last_eval = st.session_state.eval_result
        st.warning(f"🔄 **再挑戦中 (前回スコア: {last_eval.get('score', 0)}点)** — 前回のフィードバックを参考に回答を改善しましょう。")
        
        with st.expander("💡 再回答のための着眼点ガイド & 前回のフィードバック", expanded=True):
            st.markdown(f"**前回のコーチアドバイス:**\n> {last_eval.get('feedback', '')}")
            
            misses = last_eval.get("miss_categories", [])
            if misses:
                st.markdown("**前回の見落としポイント:** " + " ".join([f"`{m}`" for m in misses]))

            st.markdown("""
            ---
            **【丸パクリせずにスコアを伸ばすための3つの視点】**
            1. 🔍 **コードのどの行に注目するか？**
               - 対象コード内の `if`, `assert`, `raise`, `return` などの条件分岐と結果に直接注目します。
            2. ❓ **前回どの観点が抜けていたか？**
               - 「例外クラス名（TypeError等）」や「戻り値の計算仕様」など、見落としていた要素を付け足します。
            3. 🗣️ **具体化のポイント**:
               - 「〜をチェックしている」だけでなく、**「どんな値の時に」「どうなるか」** まで具体的に書いてみましょう。
            """)

    st.divider()

    # 3. ユーザー回答テキストエリア
    st.subheader("✏️ あなたの回答")
    st.caption("コードを書く必要はありません。関数の目的、処理の流れ、引数や戻り値の仕様を文章で説明してください。")
    
    answer_text = st.text_area(
        "回答入力",
        height=180,
        placeholder="例: この関数は数値aとbを受け取り、0除算や型の不正をチェックした上で割り算の結果を返します...",
        key="answer_input_area"
    )

    col_sub, col_skip = st.columns([3, 1])
    with col_sub:
        if st.button("📤 回答を提出", type="primary", use_container_width=True, disabled=not answer_text.strip()):
            st.session_state.user_answer = answer_text
            st.session_state.step = "evaluate"
            st.rerun()
    with col_skip:
        if st.button("スキップ", use_container_width=True):
            st.session_state.user_answer = "(パス)"
            st.session_state.step = "evaluate"
            st.rerun()

# 【画面4: 採点評価中】
elif st.session_state.step == "evaluate":
    st.title("⏳ コーチが回答を採点中...")
    chunks = st.session_state.session_data["chunks"]
    current_idx = st.session_state.current_chunk_idx
    chunk_obj = CodeChunk(**chunks[current_idx])

    with st.spinner("項目別スコアリングとフィードバックを作成しています..."):
        eval_res = st.session_state.core.evaluate_answer_and_save(
            session_id=st.session_state.session_data["session"]["id"],
            chunk=chunk_obj,
            question_data=st.session_state.current_question,
            user_answer=st.session_state.user_answer,
            target_score=st.session_state.target_score
        )
        st.session_state.eval_result = eval_res
        st.session_state.step = "scored"
        st.rerun()

# 【画面5: 採点結果表示画面】
elif st.session_state.step == "scored":
    chunks = st.session_state.session_data["chunks"]
    current_idx = st.session_state.current_chunk_idx
    chunk_obj = CodeChunk(**chunks[current_idx])
    eval_res = st.session_state.eval_result
    score = eval_res["score"]
    passed = eval_res["is_passed"]

    st.title("📊 採点結果")

    col_s1, col_s2, col_s3 = st.columns([1, 1, 2])
    with col_s1:
        st.metric("得点", f"{score} / 100", delta=f"目標 {st.session_state.target_score}点")
    with col_s2:
        if passed:
            st.success("## ✅ 合格", icon="🎉")
        else:
            st.error("## 📖 要復習", icon="💡")

    with col_s3:
        history = eval_res.get("history_summary", [])
        if len(history) > 1:
            prev_score = history[-2]["score"]
            diff = score - prev_score
            diff_str = f"+{diff}" if diff >= 0 else f"{diff}"
            st.info(f"📈 **成長ログ**: 前回 `{prev_score}点` → 今回 `{score}点` ({diff_str}点)")
        else:
            st.info("📈 **成長ログ**: 初回挑戦のスコアが記録されました")

    st.divider()

    # 提出回答
    st.subheader("✏️ あなたの提出回答")
    st.markdown(f"> {st.session_state.user_answer}")

    st.divider()

    # 項目別スコア詳細
    st.subheader("📋 項目別採点詳細")
    score_details = eval_res.get("score_details", [])
    if score_details:
        for item in score_details:
            col_name, col_sc, col_reason = st.columns([2, 1, 4])
            with col_name:
                st.markdown(f"**{item.get('name', '項目')}**")
            with col_sc:
                st.caption(f"{item.get('score', 0)} / {item.get('max', 25)} 点")
            with col_reason:
                st.write(item.get('reason', ''))

    # ミスカテゴリ
    miss_cats = eval_res.get("miss_categories", [])
    if miss_cats:
        st.markdown("**見落としたポイント・ミスタグ:** " + " ".join([f"`{cat}`" for cat in miss_cats]))

    st.divider()

    # 💬 コーチからのアドバイス
    st.subheader("💬 コーチからのアドバイス")
    if passed:
        st.success(eval_res.get("feedback", "素晴らしい回答です！次へ進みましょう。"))
    else:
        st.warning(eval_res.get("feedback", "惜しい！ヒントを確認して再チャレンジしてみましょう。"))

    st.divider()

    col_next, col_retry = st.columns(2)
    with col_next:
        if passed or current_idx + 1 < len(chunks):
            btn_label = "▶️ 次のChunkへ進む" if current_idx + 1 < len(chunks) else "🎉 全Chunk完了（結果画面へ）"
            if st.button(btn_label, type="primary", use_container_width=True):
                st.session_state.current_chunk_idx += 1
                if st.session_state.current_chunk_idx >= len(chunks):
                    st.session_state.core.finish_session(st.session_state.session_data["session"]["id"], status="completed")
                    st.session_state.step = "finish"
                else:
                    st.session_state.step = "generate_question"
                st.rerun()
    with col_retry:
        if st.button("🔄 もう一度回答する (学び直し)", use_container_width=True):
            st.session_state.step = "question"
            st.rerun()

# 【画面6: 全セッション完了画面】
elif st.session_state.step == "finish":
    st.balloons()
    st.title("🎉 お疲れ様でした！")
    st.success("指定されたファイルのすべての Chunk に対する理解度テストが完了しました。")

    if st.session_state.session_data:
        session_id = st.session_state.session_data["session"]["id"]
        st.subheader("📜 今セッションの全成績履歴")
        with st.container(border=True):
            st.caption("セッション内の全回答ログは SQLite `dedoubt.db` に永続保存されています。")

    if st.button("🔄 最初の画面に戻る", type="primary"):
        st.session_state.step = "init"
        st.session_state.session_data = None
        st.rerun()
