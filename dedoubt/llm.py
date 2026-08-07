"""
DeDoubt — LLMクライアント & プロンプト構築モジュール (dedoubt/llm.py)

- LLMClient 抽象層 (OllamaClient / MockLLMClient)
- コードに応じた「動的評価項目（ルーブリック）」の生成
- 無解・否定文章に対する高精度0点ガード
- 言及がない項目への厳格な0点判定
"""
import json
import requests
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dedoubt.parser import CodeChunk

class LLMClient(ABC):
    """LLM通信を抽象化する基底クラス (管理番号5-1-1)"""
    @abstractmethod
    def ask(self, prompt: str) -> str:
        pass

class OllamaClient(LLMClient):
    """Ollama用の実実装"""
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def ask(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0}
                },
                timeout=35
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            raise RuntimeError(f"Ollama API Connection Error: {e}")

def is_unknown_or_empty_answer(answer: str) -> bool:
    """「わからない」「〜かわからない」「パス」などの無解・不明フレーズを高精度で判定"""
    cleaned = answer.strip().lower()
    if not cleaned or len(cleaned) < 2:
        return True

    # 明確な無知・不明フレーズに限定
    unknown_patterns = [
        r"わから[なにはね]",
        r"分から[なにはね]",
        r"解ら[なにはね]",
        r"わからん",
        r"分からん",
        r"解らん",
        r"理解でき[なにい]",
        r"理解出来[なにい]",
        r"知ら[なにいん]",
        r"不明",
        r"^パス$",
        r"^\?\?\?*$",
        r"don'?t know",
        r"no idea",
        r"^unknown$",
        r"^pass$"
    ]
    for pattern in unknown_patterns:
        if re.search(pattern, cleaned):
            return True
    return False

class MockLLMClient(LLMClient):
    """ローカルOllama未起動時やデモ用の高精度フィードバックモック"""
    def ask(self, prompt: str) -> str:
        # ──────────────────────────────────────────
        # 【タスク: 質問生成】
        # ──────────────────────────────────────────
        if "【タスク: 質問生成】" in prompt:
            if "divide_with_raise" in prompt:
                return json.dumps({
                    "question": "`divide_with_raise()` 関数は引数 `a` と `b` に対してどのような例外検証(raise)を行い、どのような結果を返すか説明してください。",
                    "axis": "構造軸（物理的内容）",
                    "difficulty": "標準",
                    "rubric": [
                        {"name": "引数の型チェック (isinstance)", "max": 25},
                        {"name": "0除算チェック (b == 0)", "max": 25},
                        {"name": "送出例外クラス (TypeError / ValueError)", "max": 25},
                        {"name": "計算結果の返却仕様 (a / b)", "max": 25}
                    ],
                    "mermaid_diagram": "graph TD\n    A[\"divide_with_raise(a, b)\"] --> B{\"a, bが数値?\"}\n    B -->|No| C[\"raise TypeError\"]\n    B -->|Yes| D{\"b == 0?\"}\n    D -->|Yes| E[\"raise ValueError\"]\n    D -->|No| F[\"return a / b\"]"
                }, ensure_ascii=False)
            elif "process_scores_with_assert" in prompt:
                return json.dumps({
                    "question": "`process_scores_with_assert()` 関数内の `assert` 文は何を目的として記述されており、どのような条件を検証しているか説明してください。",
                    "axis": "構造軸（物理的内容）",
                    "difficulty": "標準",
                    "rubric": [
                        {"name": "assert文の目的（デバッグ・内部前提条件）", "max": 35},
                        {"name": "検証条件（scoresリストが空でないこと）", "max": 35},
                        {"name": "平均値計算仕様（sum / len）", "max": 30}
                    ],
                    "mermaid_diagram": "graph TD\n    A[\"process_scores_with_assert(scores)\"] --> B{\"len(scores) > 0?\"}\n    B -->|False| C[\"raise AssertionError\"]\n    B -->|True| D[\"total / len(scores)\"]"
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "question": "このコードの目的、入力引数、および返り値の仕様について説明してください。",
                    "axis": "構造軸（物理的内容）",
                    "difficulty": "標準",
                    "rubric": [
                        {"name": "関数の目的", "max": 35},
                        {"name": "引数の仕様", "max": 35},
                        {"name": "戻り値の仕様", "max": 30}
                    ],
                    "mermaid_diagram": "graph TD\n    A[\"関数呼び出し\"] --> B[\"処理実行\"]\n    B --> C[\"結果返却\"]"
                }, ensure_ascii=False)

        # ──────────────────────────────────────────
        # 【タスク: 回答採点評価】
        # ──────────────────────────────────────────
        elif "【タスク: 回答採点評価】" in prompt:
            answer = ""
            if "【ユーザーの回答】" in prompt:
                after_user = prompt.split("【ユーザーの回答】")[-1]
                if "【🚨 厳格な採点・減点ルール" in after_user:
                    answer = after_user.split("【🚨 厳格な採点・減点ルール")[0].strip()
                elif "【評価指示】" in after_user:
                    answer = after_user.split("【評価指示】")[0].strip()
                else:
                    answer = after_user.strip()
            
            # ① 「～かわからない」等の不明文章チェック (即0点)
            if is_unknown_or_empty_answer(answer):
                return json.dumps({
                    "score": 0,
                    "score_details": [
                        {"name": "関数の目的 / チェック内容", "score": 0, "max": 35, "reason": "回答に「わからない」等の不明表現が含まれるため評価できません。"},
                        {"name": "検証条件・例外クラス", "score": 0, "max": 35, "reason": "未記述のため評価対象外です。"},
                        {"name": "計算・返却仕様", "score": 0, "max": 30, "reason": "未記述のため評価対象外です。"}
                    ],
                    "miss_categories": ["理解不足・不明回答"],
                    "feedback": "💡 正直に回答いただきありがとうございます！\nコード内の `if` や `assert` の行を読みながら、どのような条件が検証されているか言葉にしてみましょう。",
                    "is_passed": False
                }, ensure_ascii=False)

            # ② divide_with_raise に対する厳格採点
            if "divide_with_raise" in prompt:
                has_type = any(kw in answer for kw in ["isinstance", "型", "int", "float", "数値"])
                has_zero = any(kw in answer for kw in ["0除算", "ゼロ", "b == 0", "bが0", "0で割"])
                has_exc = any(kw in answer for kw in ["TypeError", "ValueError", "タイプエラー", "バリューエラー", "例外"])
                has_return = any(kw in answer for kw in ["a / b", "割り算", "除算結果", "計算結果", "結果を返"])

                # 未言及は 0 点を徹底
                score_type = 25 if has_type else 0
                score_zero = 25 if has_zero else 0
                score_exc = 20 if has_exc else 0
                score_ret = 20 if has_return else 0

                total_score = score_type + score_zero + score_exc + score_ret
                is_passed = total_score >= 70

                reason_type = "数値型(isinstance)のチェックに言及できています。" if has_type else "型チェック(isinstance)に関する記述がありません。"
                reason_zero = "0除算(b == 0)のチェックに触れられています。" if has_zero else "0除算を防止するチェックの説明が抜けています。"
                reason_exc = "例外(TypeError/ValueError)の発生について記述があります。" if has_exc else "具体的な例外クラス名(TypeError/ValueError)の記述がありません。"
                reason_ret = "割り算結果の返却仕様について説明できています。" if has_return else "計算結果(a / b)の返却に関する記述がありません。"

                misses = []
                if not has_type: misses.append("型チェックの見落とし")
                if not has_zero: misses.append("0除算チェックの見落とし")
                if not has_exc: misses.append("例外クラス名の欠落")
                if not has_return: misses.append("戻り値仕様の欠落")

                feedback = "✅ 必要な仕様が網羅されています！" if is_passed else "関数の役割の一部に触れられていますが、未記述の要素があります。\n💡 不足している検証条件や戻り値について付け足して再チャレンジしてみましょう。"

                return json.dumps({
                    "score": total_score,
                    "score_details": [
                        {"name": "引数の型チェック (isinstance)", "score": score_type, "max": 25, "reason": reason_type},
                        {"name": "0除算チェック (b == 0)", "score": score_zero, "max": 25, "reason": reason_zero},
                        {"name": "送出例外クラス (TypeError / ValueError)", "score": score_exc, "max": 25, "reason": reason_exc},
                        {"name": "計算結果の返却仕様 (a / b)", "score": score_ret, "max": 25, "reason": reason_ret}
                    ],
                    "miss_categories": misses,
                    "feedback": feedback,
                    "is_passed": is_passed
                }, ensure_ascii=False)

            # ③ process_scores_with_assert に対する厳格採点
            elif "process_scores_with_assert" in prompt:
                has_assert_purpose = any(kw in answer for kw in ["内部", "デバッグ", "前提", "バグ", "開発"])
                has_empty_check = any(kw in answer for kw in ["空", "len", "要素数", "長さ"])
                has_calc = any(kw in answer for kw in ["平均", "合計", "sum", "割り算", "平均値", "除算"])

                # 未言及項目は 0 点を徹底！（気前よく点をあげない）
                score_purp = 32 if has_assert_purpose else 0
                score_empty = 32 if has_empty_check else 0
                score_calc = 28 if has_calc else 0

                total_score = score_purp + score_empty + score_calc
                is_passed = total_score >= 70

                reason_purp = "内部前提条件の検証目的を記述できています。" if has_assert_purpose else "assertが開発時の内部チェック用であることの説明がありません。"
                reason_empty = "scoresリストが空でないことの検証に触れています。" if has_empty_check else "空リスト検証についての記載がありません。"
                reason_calc = "平均値計算(sum/len)の仕様を説明できています。" if has_calc else "平均値の算出処理に関する記述が一切含まれていません。"

                misses = []
                if not has_assert_purpose: misses.append("assertの本来目的の見落とし")
                if not has_empty_check: misses.append("検証条件の説明不足")
                if not has_calc: misses.append("平均値計算仕様の記述欠落")

                feedback = "✅ assertの検証目的と平均値計算を正確に把握できています！" if is_passed else "リストの検証部分に触れられていますが、未記述の重要仕様（平均値計算など）があります。\n💡 抜け漏れている処理についても言及を追加して再チャレンジしてみましょう。"

                return json.dumps({
                    "score": total_score,
                    "score_details": [
                        {"name": "assert文の目的（デバッグ・内部前提条件）", "score": score_purp, "max": 35, "reason": reason_purp},
                        {"name": "検証条件（scoresリストが空でないこと）", "score": score_empty, "max": 35, "reason": reason_empty},
                        {"name": "平均値計算仕様（sum / len）", "score": score_calc, "max": 30, "reason": reason_calc}
                    ],
                    "miss_categories": misses,
                    "feedback": feedback,
                    "is_passed": is_passed
                }, ensure_ascii=False)

            # 一般的な短文・部分的回答
            return json.dumps({
                "score": 30,
                "score_details": [
                    {"name": "関数の主な役割", "score": 30, "max": 50, "reason": "一部の説明に留まっています。"},
                    {"name": "詳細な条件と戻り値", "score": 0, "max": 50, "reason": "引数や戻り値の詳しい説明が欠けています。"}
                ],
                "miss_categories": ["説明の不足・抽象性"],
                "feedback": "概要の一部は触れられていますが説明が不足しています。具体的にもう一度説明してみましょう。",
                "is_passed": False
            }, ensure_ascii=False)

        return "{}"

# ──────────────────────────────────────────
# プロンプト生成ヘルパー関数
# ──────────────────────────────────────────

def build_question_prompt(chunk: CodeChunk, axis: str = "構造軸", difficulty: str = "標準", mode: str = "しっかり") -> str:
    return f"""あなたはソフトウェア開発者のコード理解度を判定する試験官です。
【タスク: 質問生成】

対象のコードChunkについて、開発者の理解度を測定するための質問、コード固有の動的評価観点（ルーブリック）、および参考Mermaid図を作成してください。

【対象コードChunk】
名前: {chunk.name} ({chunk.chunk_type})
行番号: L{chunk.start_line}-L{chunk.end_line}
```python
{chunk.code_segment}
```

【指定条件】
- 質問の軸: {axis}（構造軸=関数内の引数・処理順序・戻り値 / 関係軸=他関数との呼び出し関係）
- 難易度: {difficulty}（基礎 / 標準 / 応用）
- 学習モード: {mode}

【要求出力フォーマット (必ず以下のJSONのみを出力してください)】
※ `rubric` にはこのコードChunkで検証すべき固有の項目（合計100点満点になるように3〜4項目）を定義してください。
※ `mermaid_diagram` には ```mermaid マークダウンは含めず、純粋なMermaidの定義テキストのみを出力してください。
```json
{{
  "question": "質問文テキスト",
  "axis": "{axis}",
  "difficulty": "{difficulty}",
  "rubric": [
    {{"name": "項目1の名称", "max": 25}},
    {{"name": "項目2の名称", "max": 25}},
    {{"name": "項目3の名称", "max": 25}},
    {{"name": "項目4の名称", "max": 25}}
  ],
  "mermaid_diagram": "graph TD\\n    A[\"関数呼び出し\"] --> B[\"処理判定\"]"
}}
```
"""

def build_evaluation_prompt(chunk: CodeChunk, question: str, user_answer: str, target_score: int = 70, rubric: Optional[List[Dict[str, Any]]] = None) -> str:
    rubric_str = ""
    if rubric:
        rubric_str = "【推奨評価項目（参考）】\n" + "\n".join([f"- {r.get('name')}: 配点 {r.get('max')}点" for r in rubric])

    return f"""あなたはソフトウェア開発のコード理解度を厳格かつ公正に評価するプロの技術コーチです。
【タスク: 回答採点評価】

【対象コードChunk】
```python
{chunk.code_segment}
```

【出題された質問】
{question}

{rubric_str}

【ユーザーの回答】
{user_answer}

【🚨 厳格な採点・減点ルール (絶対順守)】
1. **無理解・回答拒否に対する即0点化**:
   - ユーザーの回答の中に「わからない」「理解できない」「パス」「???」などの拒否・無知・不明を示すフレーズが含まれる場合は、**絶対に高得点をつけてはなりません。必ず総合点 score: 0, is_passed: false** とし、全項目を0点にしてください。
2. **言及がない項目は容赦なく0点とする**:
   - ユーザーがその評価観点（例: 平均値計算、戻り値仕様、例外クラス名など）について**回答内で言及していない場合、該当項目は必ず 0点** にしてください。「一部キーワードがあるから」と気前よく点数を与えることは厳禁です。
   - 抜け漏れがある場合は必ず合格基準点（{target_score}点）未満とし、`is_passed: false` にしてください。
3. **コードに応じた動的評価項目の出力 (`score_details`)**:
   - 対象コードの内容と質問に合わせて、3〜4つの具体的な評価項目（合計100点満点）を定義し、各項目の「得点」「配点」「客観的理由」を出力してください。

【体験設計原則】
- 採点が低くてもポジティブ先行で「理解できている部分」を褒めた上、足りない要素への「次の一手ヒント」をアドバイス（feedback）に記載してください。

【要求出力フォーマット (必ず以下のJSONのみを出力してください)】
```json
{{
  "score": 45,
  "score_details": [
    {{"name": "コード固有の項目1", "score": 25, "max": 25, "reason": "・・・"}},
    {{"name": "コード固有の項目2", "score": 20, "max": 25, "reason": "・・・"}},
    {{"name": "コード固有の項目3", "score": 0, "max": 25, "reason": "説明が欠落しています。"}},
    {{"name": "コード固有の項目4", "score": 0, "max": 25, "reason": "未言及のため0点。"}}
  ],
  "miss_categories": ["特定の検証条件の見落とし"],
  "feedback": "関数の目的の一部は理解できています！\\n💡 戻り値の仕様と例外条件について言及を追加して再チャレンジしてみましょう。",
  "is_passed": false
}}
```
"""

def parse_llm_json(response_text: str) -> Dict[str, Any]:
    """LLMのレスポンスから JSON 部分を抽出してパース"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```json")[0].split("```")[0].strip() if "```" in text else text
    
    try:
        return json.loads(text)
    except Exception:
        return {
            "question": response_text,
            "score": 40,
            "score_details": [{"name": "回答の具体性", "score": 40, "max": 100, "reason": "自動パース不可のため簡易評価"}],
            "miss_categories": ["記述の曖昧さ"],
            "feedback": response_text,
            "is_passed": False
        }
