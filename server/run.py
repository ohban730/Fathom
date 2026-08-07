"""
DeDoubt サーバー起動ランナースクリプト (server/run.py)
"""
import sys
import os

# ルートディレクトリ（DeDoubt）を sys.path に追加して dedoubt パッケージを読めるようにする
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import uvicorn
from main import app

if __name__ == "__main__":
    print(f"Starting DeDoubt Server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
