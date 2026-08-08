"""
DeDoubt — ローカルSQLiteデータベース層 (dedoubt/db.py)

ER図 (v1.1) に基づく永続化ロジック
- projects
- sessions
- qa_histories
- project_analytics
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

DEFAULT_DB_PATH = "dedoubt.db"

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """テーブルの初期化と作成"""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # projects テーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            file_hash TEXT,
            overall_score REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # sessions テーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            target_score INTEGER DEFAULT 70,
            status TEXT DEFAULT 'in_progress', -- in_progress, completed, interrupted
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        """)

        # qa_histories テーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS qa_histories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            chunk_ref TEXT NOT NULL,
            question_type TEXT,
            difficulty TEXT DEFAULT '標準',
            question TEXT NOT NULL,
            mermaid_diagram TEXT,
            user_answer TEXT,
            score INTEGER DEFAULT 0,
            score_details TEXT, -- JSON
            miss_categories TEXT, -- JSON
            feedback TEXT,
            is_passed BOOLEAN DEFAULT 0,
            answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        );
        """)
        conn.commit()

def get_or_create_project(file_path: str, file_hash: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    init_db(db_path)
    now = datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            if file_hash and row["file_hash"] != file_hash:
                cursor.execute(
                    "UPDATE projects SET file_hash = ?, updated_at = ? WHERE id = ?",
                    (file_hash, now, row["id"])
                )
                conn.commit()
                cursor.execute("SELECT * FROM projects WHERE id = ?", (row["id"],))
                row = cursor.fetchone()
            return dict(row)
        
        cursor.execute(
            "INSERT INTO projects (file_path, file_hash, overall_score, created_at, updated_at) VALUES (?, ?, 0.0, ?, ?)",
            (file_path, file_hash, now, now)
        )
        conn.commit()
        project_id = cursor.lastrowid
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        return dict(cursor.fetchone())

def create_session(project_id: int, target_score: int = 70, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO sessions (project_id, target_score, status, started_at) VALUES (?, ?, 'in_progress', ?)",
            (project_id, target_score, now)
        )
        conn.commit()
        session_id = cursor.lastrowid
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(cursor.fetchone())

def update_session_status(session_id: int, status: str, db_path: str = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
            (status, now, session_id)
        )
        conn.commit()

def save_qa_history(
    session_id: int,
    chunk_ref: str,
    question_type: str,
    difficulty: str,
    question: str,
    mermaid_diagram: Optional[str],
    user_answer: str,
    score: int,
    score_details: Optional[List[Dict[str, Any]]] = None,
    miss_categories: Optional[List[str]] = None,
    feedback: str = "",
    is_passed: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    score_details_json = json.dumps(score_details or [], ensure_ascii=False)
    miss_categories_json = json.dumps(miss_categories or [], ensure_ascii=False)
    now = datetime.now().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO qa_histories (
                session_id, chunk_ref, question_type, difficulty,
                question, mermaid_diagram, user_answer, score,
                score_details, miss_categories, feedback, is_passed, answered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, chunk_ref, question_type, difficulty,
                question, mermaid_diagram, user_answer, score,
                score_details_json, miss_categories_json, feedback, int(is_passed), now
            )
        )
        conn.commit()
        return cursor.lastrowid

def get_qa_histories_for_session(session_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM qa_histories WHERE session_id = ? ORDER BY id ASC", (session_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["score_details"] = json.loads(d["score_details"]) if d["score_details"] else []
            d["miss_categories"] = json.loads(d["miss_categories"]) if d["miss_categories"] else []
            result.append(d)
        return result

def get_chunk_history_summary(chunk_ref: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT score, is_passed, answered_at FROM qa_histories WHERE chunk_ref = ? ORDER BY id ASC",
            (chunk_ref,)
        )
        return [dict(r) for r in cursor.fetchall()]

def get_project_analytics(project_id: int, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """過去の全セッションを横断分析し、Chunk別の習熟度と全体苦手カテゴリを取得"""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # プロジェクト配下の全 QA 履歴を取得
        cursor.execute(
            """
            SELECT h.* FROM qa_histories h
            JOIN sessions s ON h.session_id = s.id
            WHERE s.project_id = ?
            ORDER BY h.id ASC
            """,
            (project_id,)
        )
        rows = cursor.fetchall()

        chunk_summary = {}
        all_miss_categories = {}

        for r in rows:
            chunk = r["chunk_ref"]
            score = r["score"]
            passed = bool(r["is_passed"])
            misses = json.loads(r["miss_categories"]) if r["miss_categories"] else []

            if chunk not in chunk_summary:
                chunk_summary[chunk] = {
                    "latest_score": score,
                    "max_score": score,
                    "attempts": 1,
                    "last_passed": passed,
                    "last_feedback": r["feedback"]
                }
            else:
                chunk_summary[chunk]["latest_score"] = score
                chunk_summary[chunk]["max_score"] = max(chunk_summary[chunk]["max_score"], score)
                chunk_summary[chunk]["attempts"] += 1
                chunk_summary[chunk]["last_passed"] = passed
                chunk_summary[chunk]["last_feedback"] = r["feedback"]

            for m in misses:
                all_miss_categories[m] = all_miss_categories.get(m, 0) + 1

        # 苦手順（出現回数順）にソート
        top_weaknesses = sorted(all_miss_categories.items(), key=lambda x: x[1], reverse=True)

        return {
            "project_id": project_id,
            "chunk_summary": chunk_summary,
            "top_weaknesses": [{"category": k, "count": v} for k, v in top_weaknesses]
        }
