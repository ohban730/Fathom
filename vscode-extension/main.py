"""
DeDoubt — FastAPI ローカルバックエンドサーバー (main.py)

- Phase 2 VS Code 拡張機能向け REST API
- AST解析・Ollama/Mock採点・SQLite永続化の全ロジックを統合
"""
import sys
import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ルートディレクトリをインポートパスに追加
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dedoubt.core import DeDoubtCore
from dedoubt.parser import CodeChunk, parse_code_chunks, calculate_file_hash
from dedoubt.llm import OllamaClient, MockLLMClient, is_unknown_or_empty_answer, list_ollama_models
from dedoubt.db import (
    get_qa_histories_for_session,
    get_chunk_history_summary,
    get_recent_projects,
    get_or_create_project,
    get_project_analytics,
    get_exploration_ideas_history,
)

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

class OllamaModelSetRequest(BaseModel):
    model: str

class ExplorationGenerateRequest(BaseModel):
    file_path: str

# ──────────────────────────────────────────
# API エンドポイント
# ──────────────────────────────────────────

@app.get("/")
def read_root():
    """ルートパスアクセス時の案内"""
    return {
        "message": "DeDoubt Local Backend API Server is running!",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/api/health"
    }

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

@app.get("/api/ollama/models")
def ollama_models():
    """pull済みのOllamaモデル一覧と現在使用中のモデルを返す(UIのモデル選択ドロップダウン用)"""
    return {
        "status": "success",
        "available": list_ollama_models(),
        "current_model": core.llm.model if isinstance(core.llm, OllamaClient) else None,
        "using_ollama": isinstance(core.llm, OllamaClient)
    }

@app.post("/api/ollama/model")
def set_ollama_model(req: OllamaModelSetRequest):
    """使用するOllamaモデルを切り替える。Mockエンジン状態からの復帰(再接続)もこの経路で試みる"""
    try:
        new_client = OllamaClient(model=req.model)
        new_client.ask("test connection")
        core.llm = new_client
        return {"status": "success", "engine": f"Ollama ({core.llm.model})"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"モデルへの接続に失敗しました: {str(e)}")

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

@app.get("/api/projects/recent")
def recent_projects(limit: int = 10):
    """直近にセッションを開始した対象ファイルを新しい順に取得(フォルダをまたいだ最近のファイル一覧用)"""
    try:
        data = get_recent_projects(limit=limit, db_path=DB_PATH)
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"最近のファイル取得エラー: {str(e)}")

@app.get("/api/analytics/{project_id}")
def get_project_analytics_data(project_id: int):
    """過去の全セッションを横断分析し、Chunk別の習熟度と全体苦手カテゴリを取得"""
    try:
        analytics = get_project_analytics(project_id, db_path=DB_PATH)
        return {
            "status": "success",
            "analytics": analytics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アナリティクス取得エラー: {str(e)}")

@app.post("/api/exploration/generate")
def generate_exploration(req: ExplorationGenerateRequest):
    """全Chunk合格済みのファイルに対し、コード固有の自由課題（発展的アイデア）を生成して保存"""
    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=404, detail=f"ファイルが存在しません: {req.file_path}")

    try:
        file_hash = calculate_file_hash(req.file_path)
        chunks = parse_code_chunks(req.file_path)
        project = get_or_create_project(req.file_path, file_hash, total_chunks=len(chunks), db_path=DB_PATH)
        analytics = get_project_analytics(project["id"], db_path=DB_PATH)

        result = core.generate_exploration_ideas(
            project_id=project["id"],
            chunks=chunks,
            top_weaknesses=analytics.get("top_weaknesses", [])
        )
        return {
            "status": "success",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自由課題生成エラー: {str(e)}")

@app.get("/api/exploration/{project_id}")
def get_exploration_history(project_id: int):
    """プロジェクトの自由課題提案履歴を新しい順に取得"""
    try:
        data = get_exploration_ideas_history(project_id, db_path=DB_PATH)
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自由課題履歴取得エラー: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
