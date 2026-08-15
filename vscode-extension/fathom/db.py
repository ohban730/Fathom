"""
Fathom — ローカルSQLiteデータベース層 (fathom/db.py)

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

DEFAULT_DB_PATH = "fathom.db"

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def normalize_file_path(file_path: str) -> str:
    """Windowsのドライブレター等の大文字小文字差異で同じファイルが別プロジェクト扱いにならないよう正規化する"""
    return os.path.normcase(os.path.normpath(file_path))

def normalize_miss_categories(raw: Any) -> List[Dict[str, str]]:
    """miss_categories を必ず `[{"id": ..., "label": ...}]` の形に揃える。

    `id` は集計キー（言語非依存の安定ID）、`label` は表示用テキスト。
    苦手タグの集計は `id` の完全一致で行うため、表示文言が揺れても
    （「例外クラス名の欠落」/「例外クラス名の見落とし」）同じ弱点は1つに集約される。

    旧形式（`["戻り値仕様の欠落", ...]` という日本語文字列の配列）で保存された
    履歴もそのまま読めるよう、文字列はラベル自身をIDとみなして変換する。
    この場合、旧データ同士は従来どおり集計されるが、新形式の安定IDとは
    別タグとして並ぶ（過去の日本語ラベルからIDを機械的に復元する手段がないため、
    LLMによる遡及分類は行わない）。
    """
    result: List[Dict[str, str]] = []
    for item in raw or []:
        if isinstance(item, dict):
            cat_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
        elif isinstance(item, str):
            cat_id = label = item.strip()
        else:
            continue

        if not cat_id and not label:
            continue
        # 片方しか無い場合は互いに補完する（LLMがどちらかを省いた場合の保険）
        result.append({"id": cat_id or label, "label": label or cat_id})
    return result

def _merge_duplicate_projects(cursor: sqlite3.Cursor) -> None:
    """正規化後のパスが衝突する既存プロジェクトを1つに統合する（file_path列の正規化前に生まれた分裂の後方互換マイグレーション）"""
    cursor.execute("SELECT * FROM projects")
    rows = [dict(r) for r in cursor.fetchall()]

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        key = normalize_file_path(r["file_path"])
        groups.setdefault(key, []).append(r)

    for normalized_path, group in groups.items():
        if len(group) <= 1:
            if group[0]["file_path"] != normalized_path:
                cursor.execute("UPDATE projects SET file_path = ? WHERE id = ?", (normalized_path, group[0]["id"]))
            continue

        # 最も新しく更新されたレコードを正として残す
        group.sort(key=lambda r: r["updated_at"] or "", reverse=True)
        primary = group[0]
        duplicates = group[1:]
        for dup in duplicates:
            cursor.execute("UPDATE sessions SET project_id = ? WHERE project_id = ?", (primary["id"], dup["id"]))
            cursor.execute("UPDATE exploration_ideas SET project_id = ? WHERE project_id = ?", (primary["id"], dup["id"]))
            cursor.execute("DELETE FROM projects WHERE id = ?", (dup["id"],))

        merged_total_chunks = max([g["total_chunks"] or 0 for g in group])
        cursor.execute(
            "UPDATE projects SET file_path = ?, total_chunks = ? WHERE id = ?",
            (normalized_path, merged_total_chunks, primary["id"])
        )

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
            total_chunks INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # 既存DBへの後方互換マイグレーション（列が既にある場合はエラーを無視）
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN total_chunks INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

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

        # exploration_ideas テーブル（自由課題の提案履歴）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS exploration_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_chunk_refs TEXT, -- JSON配列
            ideas TEXT NOT NULL, -- JSON配列
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        """)

        # 既存DBへの後方互換マイグレーション: file_pathの大文字小文字差異で分裂したプロジェクトを統合
        _merge_duplicate_projects(cursor)

        conn.commit()

def get_recent_projects(limit: int = 10, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """直近にセッションを開始したプロジェクト(対象ファイル)を新しい順に取得。
    projects.updated_at はファイル内容の変更検知用であり「最後にテストした時刻」ではないため、
    sessions.started_at の最大値でソートする。"""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, MAX(s.started_at) AS last_session_at
            FROM projects p
            JOIN sessions s ON s.project_id = p.id
            GROUP BY p.id
            ORDER BY last_session_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [dict(r) for r in cursor.fetchall()]

def get_or_create_project(
    file_path: str,
    file_hash: Optional[str] = None,
    total_chunks: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    init_db(db_path)
    file_path = normalize_file_path(file_path)
    now = datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            updates = []
            params: List[Any] = []
            if file_hash and row["file_hash"] != file_hash:
                updates.append("file_hash = ?")
                params.append(file_hash)
            if total_chunks is not None and row["total_chunks"] != total_chunks:
                updates.append("total_chunks = ?")
                params.append(total_chunks)
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(row["id"])
                cursor.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
                cursor.execute("SELECT * FROM projects WHERE id = ?", (row["id"],))
                row = cursor.fetchone()
            return dict(row)

        cursor.execute(
            "INSERT INTO projects (file_path, file_hash, overall_score, total_chunks, created_at, updated_at) VALUES (?, ?, 0.0, ?, ?, ?)",
            (file_path, file_hash, total_chunks or 0, now, now)
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
    miss_categories: Optional[List[Dict[str, str]]] = None,
    feedback: str = "",
    is_passed: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    score_details_json = json.dumps(score_details or [], ensure_ascii=False)
    miss_categories_json = json.dumps(normalize_miss_categories(miss_categories), ensure_ascii=False)
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
            d["miss_categories"] = normalize_miss_categories(
                json.loads(d["miss_categories"]) if d["miss_categories"] else []
            )
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

def save_exploration_ideas(
    project_id: int,
    source_chunk_refs: List[str],
    ideas: List[Dict[str, Any]],
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """LLMが生成した自由課題（展望）の提案をプロジェクトに紐づけて保存"""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO exploration_ideas (project_id, source_chunk_refs, ideas, generated_at) VALUES (?, ?, ?, ?)",
            (project_id, json.dumps(source_chunk_refs, ensure_ascii=False), json.dumps(ideas, ensure_ascii=False), now)
        )
        conn.commit()
        return cursor.lastrowid

def get_exploration_ideas_history(project_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """プロジェクトの自由課題提案履歴を新しい順に取得"""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM exploration_ideas WHERE project_id = ? ORDER BY id DESC",
            (project_id,)
        )
        result = []
        for r in cursor.fetchall():
            d = dict(r)
            d["source_chunk_refs"] = json.loads(d["source_chunk_refs"]) if d["source_chunk_refs"] else []
            d["ideas"] = json.loads(d["ideas"]) if d["ideas"] else []
            result.append(d)
        return result

def get_project_analytics(project_id: int, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """過去の全セッションを横断分析し、Chunk別の習熟度と全体苦手カテゴリを取得"""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_chunks FROM projects WHERE id = ?", (project_id,))
        project_row = cursor.fetchone()
        total_chunks = (project_row["total_chunks"] or 0) if project_row else 0

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
        # 集計は id（言語非依存の安定ID）で行う。表示ラベルは最後に見たものを採用する
        # ため、途中で出力言語を切り替えても集計が分裂せず、表示は最新の言語に揃う。
        miss_counts: Dict[str, int] = {}
        miss_labels: Dict[str, str] = {}

        for r in rows:
            chunk = r["chunk_ref"]
            score = r["score"]
            passed = bool(r["is_passed"])
            misses = normalize_miss_categories(
                json.loads(r["miss_categories"]) if r["miss_categories"] else []
            )

            if chunk not in chunk_summary:
                chunk_summary[chunk] = {
                    "latest_score": score,
                    "max_score": score,
                    "attempts": 1,
                    "last_passed": passed,
                    "ever_passed": passed,
                    "last_feedback": r["feedback"],
                    "last_miss_categories": misses
                }
            else:
                chunk_summary[chunk]["latest_score"] = score
                chunk_summary[chunk]["max_score"] = max(chunk_summary[chunk]["max_score"], score)
                chunk_summary[chunk]["attempts"] += 1
                chunk_summary[chunk]["last_passed"] = passed
                chunk_summary[chunk]["ever_passed"] = chunk_summary[chunk]["ever_passed"] or passed
                chunk_summary[chunk]["last_feedback"] = r["feedback"]
                chunk_summary[chunk]["last_miss_categories"] = misses

            for m in misses:
                miss_counts[m["id"]] = miss_counts.get(m["id"], 0) + 1
                miss_labels[m["id"]] = m["label"]

        # 苦手順（出現回数順）にソート
        top_weaknesses = sorted(miss_counts.items(), key=lambda x: x[1], reverse=True)

        # 「自由課題」の解禁は直近の合否ではなく、過去に一度でも合格したことがあるかで判定する
        # (テスト中の適当な1回の回答で「未達成」に巻き戻ってしまうのを防ぐため)
        ever_passed_count = sum(1 for c in chunk_summary.values() if c["ever_passed"])
        is_fully_mastered = bool(total_chunks > 0 and ever_passed_count >= total_chunks)

        return {
            "project_id": project_id,
            "chunk_summary": chunk_summary,
            "top_weaknesses": [
                {"id": k, "label": miss_labels.get(k, k), "count": v} for k, v in top_weaknesses
            ],
            "total_chunks": total_chunks,
            "is_fully_mastered": is_fully_mastered
        }
