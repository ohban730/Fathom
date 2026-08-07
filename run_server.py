"""
DeDoubt サーバー一括起動スクリプト (run_server.py)
"""
import sys
import os
import uvicorn

# ルートディレクトリと server ディレクトリを sys.path に追加
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(ROOT_DIR, "server")

sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SERVER_DIR)

from server.main import app

if __name__ == "__main__":
    print(f"🚀 Starting DeDoubt Server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
