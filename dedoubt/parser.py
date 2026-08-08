"""
DeDoubt — AST解析 & Chunk分割モジュール (dedoubt/parser.py)

Python の ast モジュールを利用し、ソースコードから関数・クラスの Chunk を自動抽出する。
ファイルハッシュ (SHA256) の算定機能も提供。
"""
import ast
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Optional

@dataclass
class CodeChunk:
    name: str
    chunk_type: str  # 'function' | 'class' | 'entrypoint'
    start_line: int
    end_line: int
    code_segment: str
    args: List[str]
    docstring: Optional[str] = None
    methods: Optional[List[str]] = None
    calls: List[str] = field(default_factory=list)  # このファイル内で呼び出している他Chunkの名前

    def to_dict(self):
        return asdict(self)

def calculate_file_hash(file_path: str) -> str:
    """ファイルの SHA256 ハッシュ値を計算"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def _is_main_guard(node: ast.AST) -> bool:
    """`if __name__ == "__main__":` ガード句かどうかを判定"""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name) and test.left.id == "__name__"
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )

def _called_names(nodes: List[ast.AST]) -> set:
    """ノード群の中で直接呼び出されている識別子名（`foo()`形式のみ）を収集する。
    `obj.method()`のような属性呼び出しは、無関係な同名関数との誤検出を避けるため対象外とする。"""
    called = set()
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                called.add(child.func.id)
    return called

def parse_code_chunks(file_path: str) -> List[CodeChunk]:
    """ソースコードファイルから CodeChunk のリストを生成"""
    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    lines = source_code.splitlines()
    tree = ast.parse(source_code, filename=file_path)
    chunks: List[CodeChunk] = []
    entrypoint_nodes: List[ast.AST] = []
    # 各Chunkと、呼び出し関係の検出に使う元ASTノード（複数行にまたがるentrypointはリスト）の対応
    chunk_source_nodes: List[tuple] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            # トップレベル関数
            segment_lines = lines[node.lineno - 1 : node.end_lineno]
            segment_code = "\n".join(segment_lines)
            args = [arg.arg for arg in node.args.args]
            docstring = ast.get_docstring(node)

            chunk = CodeChunk(
                name=node.name,
                chunk_type="function",
                start_line=node.lineno,
                end_line=node.end_lineno,
                code_segment=segment_code,
                args=args,
                docstring=docstring,
            )
            chunks.append(chunk)
            chunk_source_nodes.append((chunk, [node]))

        elif isinstance(node, ast.ClassDef):
            # クラス定義
            segment_lines = lines[node.lineno - 1 : node.end_lineno]
            segment_code = "\n".join(segment_lines)
            methods = [
                n.name for n in node.body
                if isinstance(n, ast.FunctionDef)
            ]
            docstring = ast.get_docstring(node)

            chunk = CodeChunk(
                name=node.name,
                chunk_type="class",
                start_line=node.lineno,
                end_line=node.end_lineno,
                code_segment=segment_code,
                args=[],
                docstring=docstring,
                methods=methods,
            )
            chunks.append(chunk)
            chunk_source_nodes.append((chunk, [node]))

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # import文は学習対象から除外
            continue

        else:
            # 関数・クラス定義以外のトップレベル処理
            # （if __name__ == "__main__": ブロックや、手続き型スクリプトの実行コード）
            entrypoint_nodes.append(node)

    if entrypoint_nodes:
        # 「関数・クラスがどう呼び出され、組み合わさって使われるか」＝関係軸の教材として
        # 1つの追加Chunkにまとめる
        start_line = min(n.lineno for n in entrypoint_nodes)
        end_line = max(n.end_lineno for n in entrypoint_nodes)
        segment_lines = lines[start_line - 1 : end_line]
        segment_code = "\n".join(segment_lines)

        is_main_guard_only = len(entrypoint_nodes) == 1 and _is_main_guard(entrypoint_nodes[0])
        name = "__main__" if is_main_guard_only else "モジュールの実行フロー"

        entrypoint_chunk = CodeChunk(
            name=name,
            chunk_type="entrypoint",
            start_line=start_line,
            end_line=end_line,
            code_segment=segment_code,
            args=[],
            docstring=None,
        )
        chunks.append(entrypoint_chunk)
        chunk_source_nodes.append((entrypoint_chunk, entrypoint_nodes))

    # 呼び出し関係の検出（全Chunk名が出揃った後の2パス目。定義順に関係なく解決できる）
    known_names = {c.name for c in chunks}
    for chunk, source_nodes in chunk_source_nodes:
        called = _called_names(source_nodes) & known_names
        called.discard(chunk.name)  # 自己再帰は対象外
        chunk.calls = sorted(called)

    return chunks
