"""
DeDoubt — コアセッション制御モジュール (dedoubt/core.py)

- ファイルのプロジェクト登録・ハッシュ比較
- セッションの開始・状態遷移（進行中 / 完了 / 中断）
- Chunk単位の Q&A 進行（動的評価項目ルーブリックの管理）
- 過去スコア比較（成長の可視化データ生成）
"""
import os
from typing import List, Dict, Any, Optional
from dedoubt.parser import parse_code_chunks, calculate_file_hash, CodeChunk
from dedoubt.db import (
    get_or_create_project,
    create_session,
    update_session_status,
    save_qa_history,
    get_qa_histories_for_session,
    get_chunk_history_summary,
    save_exploration_ideas,
)
from dedoubt.llm import (
    LLMClient,
    OllamaClient,
    MockLLMClient,
    build_question_prompt,
    build_evaluation_prompt,
    build_exploration_prompt,
    parse_llm_json,
    is_unknown_or_empty_answer,
)

class DeDoubtCore:
    def __init__(self, db_path: str = "dedoubt.db", llm_client: Optional[LLMClient] = None):
        self.db_path = db_path
        if llm_client:
            self.llm = llm_client
        else:
            # デフォルトで OllamaClient を使用し、接続不可なら MockLLMClient に切り替え。
            # OllamaClient()自体の内部で/api/tagsによる疎通確認を行うため、ここでは
            # 実際にプロンプトを送って生成させない(大きいモデルの初回ロードで
            # 数十秒かかることがあり、起動時のテストとしては重すぎるため)。
            try:
                self.llm = OllamaClient()
            except Exception:
                self.llm = MockLLMClient()

    def start_session_for_file(self, file_path: str, target_score: int = 70) -> Dict[str, Any]:
        """ファイルを読み込み、AST解析をしてセッションを開始"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = calculate_file_hash(file_path)
        chunks = parse_code_chunks(file_path)
        project = get_or_create_project(file_path, file_hash, total_chunks=len(chunks), db_path=self.db_path)
        session = create_session(project["id"], target_score, db_path=self.db_path)

        return {
            "project": project,
            "session": session,
            "chunks": [c.to_dict() for c in chunks],
            "current_chunk_index": 0
        }

    def generate_question_for_chunk(
        self,
        chunk: CodeChunk,
        axis: str = "構造軸",
        difficulty: str = "標準",
        mode: str = "しっかり"
    ) -> Dict[str, Any]:
        """指定した Chunk に対する質問と動的ルーブリックを生成"""
        prompt = build_question_prompt(chunk, axis=axis, difficulty=difficulty, mode=mode)
        response = self.llm.ask(prompt)
        parsed = parse_llm_json(response)

        return {
            "question": parsed.get("question", "コードの処理内容を説明してください。"),
            "axis": parsed.get("axis", axis),
            "difficulty": parsed.get("difficulty", difficulty),
            "rubric": parsed.get("rubric", []),
            "mermaid_diagram": parsed.get("mermaid_diagram", None)
        }

    def evaluate_answer_and_save(
        self,
        session_id: int,
        chunk: CodeChunk,
        question_data: Dict[str, Any],
        user_answer: str,
        target_score: int = 70
    ) -> Dict[str, Any]:
        """ユーザーの回答を動的観点に基づいて厳格採点し、DBに保存"""
        question_text = question_data["question"]
        rubric = question_data.get("rubric", [])

        # 「わからない」「パス」などの無解・無効回答に対するガード (0点)
        if is_unknown_or_empty_answer(user_answer):
            score = 0
            is_passed = False
            score_details = [
                {"name": r.get("name", "評価項目"), "score": 0, "max": r.get("max", 25), "reason": "回答が「わからない」または未入力のため評価できません。"}
                for r in (rubric or [{"name": "仕様理解", "max": 100}])
            ]
            miss_categories = ["内容未記述・理解不足"]
            feedback = "💡 「わからない」と正直に回答していただきありがとうございます！\n関数のコードを見ながら、どのようなチェックが行われているかを言葉にしてみましょう。"
        else:
            prompt = build_evaluation_prompt(chunk, question_text, user_answer, target_score=target_score, rubric=rubric)
            response = self.llm.ask(prompt)
            parsed = parse_llm_json(response)

            score_details = parsed.get("score_details", [])
            # 項目別スコアの合計値でスコアを厳格計算（未計算の場合）
            if score_details:
                calculated_score = sum(int(item.get("score", 0)) for item in score_details)
                score = calculated_score
            else:
                score = int(parsed.get("score", 45))

            is_passed = bool(score >= target_score)
            miss_categories = parsed.get("miss_categories", [])
            feedback = parsed.get("feedback", "")

        qa_id = save_qa_history(
            session_id=session_id,
            chunk_ref=chunk.name,
            question_type=question_data.get("axis", "構造軸"),
            difficulty=question_data.get("difficulty", "標準"),
            question=question_text,
            mermaid_diagram=question_data.get("mermaid_diagram"),
            user_answer=user_answer,
            score=score,
            score_details=score_details,
            miss_categories=miss_categories,
            feedback=feedback,
            is_passed=is_passed,
            db_path=self.db_path
        )

        # 過去スコア比較（成長の可視化）
        history_summary = get_chunk_history_summary(chunk.name, db_path=self.db_path)

        return {
            "qa_id": qa_id,
            "score": score,
            "is_passed": is_passed,
            "score_details": score_details,
            "miss_categories": miss_categories,
            "feedback": feedback,
            "history_summary": history_summary
        }

    def generate_exploration_ideas(
        self,
        project_id: int,
        chunks: List[CodeChunk],
        top_weaknesses: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """全Chunk合格後、コード固有の自由課題（発展的アイデア）をLLMに生成させDBに保存する"""
        prompt = build_exploration_prompt(chunks, top_weaknesses=top_weaknesses)
        response = self.llm.ask(prompt)
        parsed = parse_llm_json(response)

        ideas = parsed.get("ideas")
        if not ideas:
            # フェイクの提案をでっち上げず、明示的にエラーとして扱う
            raise ValueError("自由課題の生成に失敗しました（LLM応答を解釈できませんでした）")

        source_chunk_refs = [c.name for c in chunks]
        idea_id = save_exploration_ideas(project_id, source_chunk_refs, ideas, db_path=self.db_path)

        return {
            "id": idea_id,
            "project_id": project_id,
            "source_chunk_refs": source_chunk_refs,
            "ideas": ideas
        }

    def finish_session(self, session_id: int, status: str = "completed") -> None:
        """セッションを完了または中断として更新"""
        update_session_status(session_id, status, db_path=self.db_path)
