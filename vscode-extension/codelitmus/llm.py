"""
CodeLitmus — LLMクライアント & プロンプト構築モジュール (codelitmus/llm.py)

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
from codelitmus.parser import CodeChunk

class LLMClient(ABC):
    """LLM通信を抽象化する基底クラス (管理番号5-1-1)"""
    @abstractmethod
    def ask(self, prompt: str) -> str:
        pass

def list_ollama_models(base_url: str = "http://localhost:11434") -> List[str]:
    """Ollamaに実際にpull済みのモデル名一覧を取得する。未起動・取得失敗時は空リスト。"""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []

class OllamaClient(LLMClient):
    """Ollama用の実実装。

    modelを明示しない場合、特定のモデル名（例: "llama3"）をハードコードせず、
    実際にpull済みのモデルから自動選択する（ユーザーの環境ごとに異なるため）。
    """
    def __init__(self, model: Optional[str] = None, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        if model:
            self.model = model
        else:
            available = list_ollama_models(base_url)
            if not available:
                raise RuntimeError("Ollamaに接続できないか、pull済みのモデルが1つもありません。")
            self.model = available[0]

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
                timeout=120
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
            if "名前: __main__" in prompt:
                return json.dumps({
                    "question": "この `if __name__ == \"__main__\":` ブロックは `divide_with_raise()` と `process_scores_with_assert()` をそれぞれどのような引数・順序で呼び出しており、発生した例外をどう捕捉していますか？呼び出しの流れを説明してください。",
                    "axis": "関係軸",
                    "difficulty": "標準",
                    "rubric": [
                        {"name": "divide_with_raise()の呼び出しと例外捕捉(ValueError/TypeError)", "max": 40},
                        {"name": "process_scores_with_assert()の呼び出しと例外捕捉(AssertionError)", "max": 40},
                        {"name": "try-exceptによる呼び出し順序・エラーハンドリングの流れ", "max": 20}
                    ],
                    "mermaid_diagram": "sequenceDiagram\n    participant Main as __main__\n    participant D as divide_with_raise\n    participant P as process_scores_with_assert\n    Main->>D: divide_with_raise(10, 0)\n    D-->>Main: raise ValueError\n    Main->>D: divide_with_raise(10, \"5\")\n    D-->>Main: raise TypeError\n    Main->>P: process_scores_with_assert([])\n    P-->>Main: raise AssertionError"
                }, ensure_ascii=False)
            elif "名前: モジュールの実行フロー" in prompt:
                return json.dumps({
                    "question": "このスクリプトは `iter()` と `next()` をどのような順序で使ってリストからデータを取り出しており、要素が尽きたときにどのような例外が発生し、それが `for` 文の裏側の動作とどう対応していますか？説明してください。",
                    "axis": "関係軸",
                    "difficulty": "標準",
                    "rubric": [
                        {"name": "iter()でイテレータを生成する仕組み", "max": 25},
                        {"name": "next()による1件ずつの取り出しと呼び出し回数", "max": 25},
                        {"name": "要素が尽きた際のStopIteration発生", "max": 25},
                        {"name": "forループとiter/nextの対応関係", "max": 25}
                    ],
                    "mermaid_diagram": "sequenceDiagram\n    participant S as スクリプト\n    participant It as fruits_iterator\n    S->>It: iter(fruits)\n    S->>It: next() (1回目)\n    It-->>S: \"apple\"\n    S->>It: next() (2回目)\n    It-->>S: \"banana\"\n    S->>It: next() (3回目)\n    It-->>S: \"cherry\"\n    S->>It: next() (4回目)\n    It-->>S: raise StopIteration"
                }, ensure_ascii=False)
            elif "名前: divide_with_raise" in prompt:
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
            elif "名前: process_scores_with_assert" in prompt:
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

            # ② __main__ エントリーポイント（呼び出し関係）に対する厳格採点
            if "対象Chunk名: __main__" in prompt:
                has_divide = any(kw in answer for kw in ["divide_with_raise", "ValueError", "TypeError", "0で割", "型"])
                has_assert_call = any(kw in answer for kw in ["process_scores_with_assert", "AssertionError", "assert", "空リスト", "空の"])
                has_order = any(kw in answer for kw in ["順番", "順序", "try", "except", "呼び出し", "流れ", "捕捉"])

                score_divide = 40 if has_divide else 0
                score_assert_call = 40 if has_assert_call else 0
                score_order = 20 if has_order else 0
                total_score = score_divide + score_assert_call + score_order
                is_passed = total_score >= 70

                misses = []
                if not has_divide: misses.append("divide_with_raise呼び出し・例外の見落とし")
                if not has_assert_call: misses.append("process_scores_with_assert呼び出し・例外の見落とし")
                if not has_order: misses.append("呼び出し順序・エラーハンドリングの流れの説明不足")

                feedback = "✅ 2つの関数がどう呼ばれ、例外がどう捕捉されているか正確に説明できています！" if is_passed else "呼び出されている関数の一部には触れられていますが、例外の捕捉や呼び出しの流れの説明が不足しています。\n💡 try-exceptで何を捕まえているか、どの順番で呼ばれているかに注目してみましょう。"

                return json.dumps({
                    "score": total_score,
                    "score_details": [
                        {"name": "divide_with_raise()の呼び出しと例外捕捉(ValueError/TypeError)", "score": score_divide, "max": 40, "reason": "divide_with_raiseの呼び出しと例外の説明ができています。" if has_divide else "divide_with_raiseの呼び出しや例外捕捉に関する記述がありません。"},
                        {"name": "process_scores_with_assert()の呼び出しと例外捕捉(AssertionError)", "score": score_assert_call, "max": 40, "reason": "process_scores_with_assertの呼び出しと例外の説明ができています。" if has_assert_call else "process_scores_with_assertの呼び出しや例外捕捉に関する記述がありません。"},
                        {"name": "try-exceptによる呼び出し順序・エラーハンドリングの流れ", "score": score_order, "max": 20, "reason": "呼び出しの順序や例外処理の流れに触れられています。" if has_order else "呼び出し順序やtry-exceptの流れに関する記述がありません。"}
                    ],
                    "miss_categories": misses,
                    "feedback": feedback,
                    "is_passed": is_passed
                }, ensure_ascii=False)

            # ②' モジュールの実行フロー（iter/next デモ等）に対する厳格採点
            elif "対象Chunk名: モジュールの実行フロー" in prompt:
                has_iter = any(kw in answer for kw in ["iter(", "イテレータ", "iterator"])
                has_next = any(kw in answer for kw in ["next(", "1つずつ", "1回目", "取り出"])
                has_stopiter = any(kw in answer for kw in ["StopIteration"])
                has_for_relation = any(kw in answer for kw in ["for", "裏側", "自動的"])

                score_iter = 25 if has_iter else 0
                score_next = 25 if has_next else 0
                score_stop = 25 if has_stopiter else 0
                score_for = 25 if has_for_relation else 0
                total_score = score_iter + score_next + score_stop + score_for
                is_passed = total_score >= 70

                misses = []
                if not has_iter: misses.append("iter()の役割の見落とし")
                if not has_next: misses.append("next()による逐次取り出しの見落とし")
                if not has_stopiter: misses.append("StopIteration発生の見落とし")
                if not has_for_relation: misses.append("forループとの対応関係の見落とし")

                feedback = "✅ iter/nextの仕組みとforループとの対応を正確に把握できています！" if is_passed else "一部の処理には触れられていますが、iter・next・StopIteration・forループの対応関係のいずれかが抜けています。\n💡 「forループの裏側で何が起きているか」に注目して説明を補ってみましょう。"

                return json.dumps({
                    "score": total_score,
                    "score_details": [
                        {"name": "iter()でイテレータを生成する仕組み", "score": score_iter, "max": 25, "reason": "iter()の役割を説明できています。" if has_iter else "iter()に関する記述がありません。"},
                        {"name": "next()による1件ずつの取り出しと呼び出し回数", "score": score_next, "max": 25, "reason": "next()による逐次取得を説明できています。" if has_next else "next()の逐次呼び出しに関する記述がありません。"},
                        {"name": "要素が尽きた際のStopIteration発生", "score": score_stop, "max": 25, "reason": "StopIterationの発生に触れています。" if has_stopiter else "StopIterationに関する記述がありません。"},
                        {"name": "forループとiter/nextの対応関係", "score": score_for, "max": 25, "reason": "forループとの対応関係を説明できています。" if has_for_relation else "forループとの対応関係に関する記述がありません。"}
                    ],
                    "miss_categories": misses,
                    "feedback": feedback,
                    "is_passed": is_passed
                }, ensure_ascii=False)

            # ③ divide_with_raise に対する厳格採点
            elif "対象Chunk名: divide_with_raise" in prompt:
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

            # ④ process_scores_with_assert に対する厳格採点
            elif "対象Chunk名: process_scores_with_assert" in prompt:
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

        # ──────────────────────────────────────────
        # 【タスク: 自由課題提案】
        # ──────────────────────────────────────────
        elif "【タスク: 自由課題提案】" in prompt:
            # 特定のファイル/関数名をハードコードせず、プロンプト内のChunk見出しから汎用的に抽出する
            chunk_names = re.findall(r"■ (\S+) \(", prompt)
            primary = chunk_names[0] if chunk_names else "このコード"
            secondary = chunk_names[1] if len(chunk_names) > 1 else primary
            return json.dumps({
                "ideas": [
                    {
                        "title": f"{primary} を別アルゴリズムで再実装してみる",
                        "description": f"{primary} の入出力仕様はそのままに、内部ロジックだけを別のアプローチに置き換えてみましょう。",
                        "hook": "同じ仕様でも実装は一通りではないことを体感できます。"
                    },
                    {
                        "title": f"{secondary} を中心に処理を可視化するツールを作る",
                        "description": f"{secondary} の呼び出しごとの状態変化をログやグラフとして出力する小さなラッパーを書いてみましょう。",
                        "hook": "コードを「読む」から「観察する」に変えると、新しい疑問が生まれます。"
                    },
                    {
                        "title": "このファイル全体をテスト可能な形に分割する",
                        "description": "各Chunkに対応するユニットテストを書き、境界値やエラー系の入力をわざと試してみましょう。",
                        "hook": "自分でテストケースを考えることで、仕様の理解がより具体的になります。"
                    }
                ]
            }, ensure_ascii=False)

        return "{}"

# ──────────────────────────────────────────
# プロンプト生成ヘルパー関数
# ──────────────────────────────────────────

def build_question_prompt(chunk: CodeChunk, axis: str = "構造軸", difficulty: str = "標準", mode: str = "しっかり") -> str:
    related_note = ""
    if chunk.calls:
        related_note = f"""
【重要: 関連Chunkとの役割分担】
このChunkは {", ".join(chunk.calls)} を呼び出していますが、これらは別のコードChunkとして個別に出題されます。
そちらの内部実装（条件分岐・計算式・例外処理など）を問う質問は絶対に作らないでください。
このChunk自身が担う範囲（呼び出す順序、渡すデータ、受け取った結果をどう次に使うか、全体の流れの中での役割）にのみ焦点を当ててください。
"""

    return f"""あなたはソフトウェア開発者のコード理解度を判定する試験官です。
【タスク: 質問生成】

対象のコードChunkについて、開発者の理解度を測定するための質問、コード固有の動的評価観点（ルーブリック）、および参考Mermaid図を作成してください。

【対象コードChunk】
名前: {chunk.name} ({chunk.chunk_type})
行番号: L{chunk.start_line}-L{chunk.end_line}
```python
{chunk.code_segment}
```
{related_note}
【指定条件】
- 質問の軸: {axis}（構造軸=関数内の引数・処理順序・戻り値 / 関係軸=他関数との呼び出し関係）
- 難易度: {difficulty}（基礎 / 標準 / 応用）
- 学習モード: {mode}
- 質問文は1つの論点に絞り、簡潔な1〜2文にしてください。「1. 2.」のような複数の問いを1つの質問に詰め込むことは禁止します。

【要求出力フォーマット (必ず以下のJSONのみを出力してください)】
※ `rubric` にはこのコードChunkで検証すべき固有の項目（合計100点満点になるように3〜4項目）を定義してください。
※ `mermaid_diagram` には ```mermaid マークダウンは含めず、純粋なMermaidの定義テキストのみを出力してください。
※ `mermaid_diagram` は必ず1行目に `graph TD` または `sequenceDiagram` などの図種別宣言を書いてください（省略するとパースに失敗します）。
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

対象Chunk名: {chunk.name}

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

def build_exploration_prompt(chunks: List[CodeChunk], top_weaknesses: Optional[List[Dict[str, Any]]] = None) -> str:
    """全Chunk合格後に提示する、自由課題（Bloom創造レベルの発展的アイデア）提案用プロンプトを構築"""
    chunk_overview = "\n\n".join([
        f"■ {c.name} ({c.chunk_type})\n呼び出し先: {', '.join(c.calls) if c.calls else 'なし'}\n```python\n{c.code_segment}\n```"
        for c in chunks
    ])

    weakness_note = ""
    if top_weaknesses:
        tags = ", ".join([w.get("category", "") for w in top_weaknesses[:5] if w.get("category")])
        if tags:
            weakness_note = f"\n【学習者がこれまで苦手としてきた観点】\n{tags}\n（得意な部分を土台にしつつ、これらの観点を自然に使う課題があれば歓迎します）\n"

    return f"""あなたはソフトウェア開発の学習コーチです。
【タスク: 自由課題提案】

学習者はこのコードの全Chunkについて、構造・仕様の理解度チェックに合格しました。
このコードを土台に、学習者が「次に自分で手を動かしてみたくなる」ような、このコード固有の自由課題（発展的な作り込みのアイデア）を3件提案してください。
これはBloomの分類学でいう最上位「⑥創造」レベルの課題であり、正誤を採点するものではありません。正解を教えるのではなく、好奇心を刺激する提案にしてください。

【対象コードの全体構造】
{chunk_overview}
{weakness_note}
【提案の条件】
- 提案は必ずこのコードの実際の関数名・処理内容に言及し、一般論（例:「エラーハンドリングを学びましょう」）で終わらせないこと
- 既存コードを壊す指示ではなく、拡張・別実装・応用の方向性を示すこと
- 各提案は「タイトル」「何をするか(2〜3文)」「なぜ面白いか・何が身につくか(1文)」で構成すること

【要求出力フォーマット (必ず以下のJSONのみを出力してください)】
```json
{{
  "ideas": [
    {{"title": "提案タイトル", "description": "具体的に何を作る/変更するか", "hook": "なぜ面白いか・何が身につくか"}},
    {{"title": "...", "description": "...", "hook": "..."}},
    {{"title": "...", "description": "...", "hook": "..."}}
  ]
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
