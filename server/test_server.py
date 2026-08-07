"""
FastAPI サーバーの自動検証スクリプト (server/test_server.py)
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_backend_apis():
    print("=== 1. Health Check Test ===")
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    print("Health:", r.json())

    print("\n=== 2. Session Start Test ===")
    file_path = r"C:\Users\owner\Documents\lab\DeDoughtスプレッドシート\検証用ファイル\assert-and-raise.py"
    r = requests.post(f"{BASE_URL}/api/session/start", json={"file_path": file_path, "target_score": 70})
    assert r.status_code == 200
    session_res = r.json()["data"]
    print("Project ID:", session_res["project"]["id"], "Session ID:", session_res["session"]["id"])
    print("Chunks count:", len(session_res["chunks"]))

    chunk = session_res["chunks"][0]

    print("\n=== 3. Question Generate Test ===")
    r = requests.post(f"{BASE_URL}/api/question/generate", json={"chunk": chunk, "axis": "構造軸"})
    assert r.status_code == 200
    q_res = r.json()["data"]
    print("Question:", q_res["question"])
    print("Rubric items:", len(q_res.get("rubric", [])))

    print("\n=== 4. Evaluate Answer Test (Strict Zero Test) ===")
    r = requests.post(f"{BASE_URL}/api/answer/evaluate", json={
        "session_id": session_res["session"]["id"],
        "chunk": chunk,
        "question_data": q_res,
        "user_answer": "わからない",
        "target_score": 70
    })
    assert r.status_code == 200
    e_res = r.json()["data"]
    print("Score:", e_res["score"], "Passed:", e_res["is_passed"])
    assert e_res["score"] == 0

    print("\n=== 5. Evaluate Answer Test (Partial Strict Test) ===")
    r = requests.post(f"{BASE_URL}/api/answer/evaluate", json={
        "session_id": session_res["session"]["id"],
        "chunk": chunk,
        "question_data": q_res,
        "user_answer": "aがintでなければタイプエラーを出力する",
        "target_score": 70
    })
    assert r.status_code == 200
    e_res2 = r.json()["data"]
    print("Score:", e_res2["score"], "Passed:", e_res2["is_passed"])
    assert e_res2["score"] == 45

    print("\nSUCCESS: All API endpoints verified!")

if __name__ == "__main__":
    test_backend_apis()
