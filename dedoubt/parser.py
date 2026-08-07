"""
DeDoubt — AST解析 & Chunk分割モジュール (dedoubt/parser.py)

Python の ast モジュールを利用し、ソースコードから関数・クラスの Chunk を自動抽出する。
ファイルハッシュ (SHA256) の算定機能も提供。
"""
import ast
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class CodeChunk:
    name: str
    chunk_type: str  # 'function' | 'class'
    start_line: int
    end_line: int
    code_segment: str
    args: List[str]
    docstring: Optional[str] = None
    methods: Optional[List[str]] = None

    def to_dict(self):
        return asdict(self)

def calculate_file_hash(file_path: str) -> str:
    """ファイルの SHA256 ハッシュ値を計算"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def parse_code_chunks(file_path: str) -> List[CodeChunk]:
    """ソースコードファイルから CodeChunk のリストを生成"""
    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    lines = source_code.splitlines()
    tree = ast.parse(source_code, filename=file_path)
    chunks: List[CodeChunk] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            # トップレベル関数
            segment_lines = lines[node.lineno - 1 : node.end_lineno]
            segment_code = "\n".join(segment_lines)
            args = [arg.arg for arg in node.args.args]
            docstring = ast.get_docstring(node)

            chunks.append(CodeChunk(
                name=node.name,
                chunk_type="function",
                start_line=node.lineno,
                end_line=node.end_lineno,
                code_segment=segment_code,
                args=args,
                docstring=docstring,
            ))

        elif isinstance(node, ast.ClassDef):
            # クラス定義
            segment_lines = lines[node.lineno - 1 : node.end_lineno]
            segment_code = "\n".join(segment_lines)
            methods = [
                n.name for n in node.body
                if isinstance(n, ast.FunctionDef)
            ]
            docstring = ast.get_docstring(node)

            chunks.append(CodeChunk(
                name=node.name,
                chunk_type="class",
                start_line=node.lineno,
                end_line=node.end_lineno,
                code_segment=segment_code,
                args=[],
                docstring=docstring,
                methods=methods,
            ))

    return chunks
