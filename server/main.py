"""
DeDoubt — FastAPI ローカルバックエンドサーバー (server/main.py)

- Phase 2 VS Code 拡張機能向け REST API
- AST解析・Ollama/Mock採点・SQLite永続化の全ロジックを統合
"""
import sys
import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ルートディレクトリの `dedoubt` パッケージをインポート可能にする
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dedoubt.core import DeDoubtCore
from dedoubt.parser import CodeChunk
from dedoubt.llm import OllamaClient, MockLLMClient, is_unknown_or_empty_answer
from dedoubt.db import get_qa_histories_for_session, get_chunk_history_summary

app = FastAPI(
    title="DeDoubt Local Backend API",
    description="VS Code 拡張機能向けコード理解サポート API",
    version="2.0.0"
)

# CORS を許可（VS Code Webview 通信対応）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DeDoubtCore インスタンスの初期化
DB_PATH = os.path.join(ROOT_DIR, "dedoubt.db")
core = DeDoubtCore(db_path=DB_PATH)

# リクエスト / レスポンスの Pydantic モデル定義

class SessionStartRequest(BaseModel):
    file_path: str
    target_score: int = 70

class QuestionGenerateRequest(BaseModel):
    chunk: Dict[str, Any]
    axis: str = "構造軸"
    difficulty: str = "標準"
    mode: str = "しっかり"

class AnswerEvaluateRequest(BaseModel):
    session_id: int
    chunk: Dict[str, Any]
    question_data: Dict[str, Any]
    user_answer: str
    target_score: int = 70

# ──────────────────────────────────────────
# API エンドポイント
# ──────────────────────────────────────────

@app.get("/api/health")
def health_check():
    """サーバー疎通・LLMエンジンステータスチェック"""
    engine_name = "Mock Engine (Demo Mode)"
    if isinstance(core.llm, OllamaClient):
        engine_name = f"Ollama ({core.llm.model})"
    
    return {
        "status": "ok",
        "engine": engine_name,
        "db_path": DB_PATH
    }

@app.post("/api/session/start")
def start_session(req: SessionStartRequest):
    """ファイルパスを受け取り、AST解析とセッション登録を実行"""
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail=f"ファイルが存在しません: {req.file_path}")

    try:
        session_info = core.start_session_for_file(req.file_path, target_score=req.target_score)
        return {
            "status": "success",
            "data": session_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"セッション開始エラー: {str(e)}")

@app.post("/api/question/generate")
def generate_question(req: QuestionGenerateRequest):
    """Chunk に対する理解度判定質問と動的ルーブリックを生成"""
    try:
        chunk_obj = CodeChunk(**req.chunk)
        q_data = core.generate_question_for_chunk(
            chunk_obj,
            axis=req.axis,
            difficulty=req.difficulty,
            mode=req.mode
        )
        return {
            "status": "success",
            "data": q_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"質問生成エラー: {str(e)}")

@app.post("/api/answer/evaluate")
def evaluate_answer(req: AnswerEvaluateRequest):
    """ユーザー回答を厳格採点し、DBに永続化"""
    try:
        chunk_obj = CodeChunk(**req.chunk)
        eval_result = core.evaluate_answer_and_save(
            session_id=req.session_id,
            chunk=chunk_obj,
            question_data=req.question_data,
            user_answer=req.user_answer,
            target_score=req.target_score
        )
        return {
            "status": "success",
            "data": eval_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回答評価エラー: {str(e)}")

@app.get("/api/dashboard/{session_id}")
def get_dashboard_data(session_id: int):
    """指定セッションの全履歴と苦手カテゴリタグを取得"""
    try:
        histories = get_qa_histories_for_session(session_id, db_path=DB_PATH)
        return {
            "status": "success",
            "session_id": session_id,
            "histories": histories
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ダッシュボード取得エラー: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
