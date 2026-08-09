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
    chunk_type: str  # 'function' | 'class' | 'entrypoint' | 'nested_function' | 'nested_class'
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
    """ノード群の中で直接呼び出されている識別子名（`foo()`形式のみ）を、
    ネストされた関数・クラス定義の内部は除外して収集する。
    ネスト定義内の呼び出しはそのネスト定義自身のChunkに属するため、
    外側のChunkの呼び出し検出に重複して含めない。
    `obj.method()`のような属性呼び出しは、無関係な同名関数との誤検出を避けるため対象外とする。"""
    called = set()

    def walk(node: ast.AST, is_root: bool) -> None:
        # is_root=Falseでこのnode自体がネストされた関数・クラス定義の場合、
        # その内部はそのネスト定義自身のChunkが担当するため辿らない
        if not is_root and isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
        for child in ast.iter_child_nodes(node):
            walk(child, is_root=False)

    for node in nodes:
        walk(node, is_root=True)
    return called

def _iter_nested_defs(node: ast.AST):
    """nodeの内部に直接ネストされている関数・クラス定義を列挙する（if/for/try等の制御構文は辿るが、
    見つかった定義自身の内部にはこの関数では立ち入らない。さらに深いネストは呼び出し元が再帰処理する）。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
            yield child
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            continue
        else:
            yield from _iter_nested_defs(child)

def _build_def_chunk(node, lines: List[str], nested: bool) -> CodeChunk:
    """FunctionDef/ClassDefノードから1つのCodeChunkを作る（トップレベル/ネストで種別を切り替える）"""
    segment_lines = lines[node.lineno - 1 : node.end_lineno]
    segment_code = "\n".join(segment_lines)
    docstring = ast.get_docstring(node)

    if isinstance(node, ast.FunctionDef):
        return CodeChunk(
            name=node.name,
            chunk_type="nested_function" if nested else "function",
            start_line=node.lineno,
            end_line=node.end_lineno,
            code_segment=segment_code,
            args=[arg.arg for arg in node.args.args],
            docstring=docstring,
        )
    else:
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        return CodeChunk(
            name=node.name,
            chunk_type="nested_class" if nested else "class",
            start_line=node.lineno,
            end_line=node.end_lineno,
            code_segment=segment_code,
            args=[],
            docstring=docstring,
            methods=methods,
        )

def _collect_def_chunks(node, lines: List[str], nested: bool, chunks: List[CodeChunk], chunk_source_nodes: List[tuple]) -> None:
    """nodeを1つのChunkとして追加し、node内部にさらにネストされた関数・クラス定義があれば
    再帰的に(任意の深さまで) 別のChunkとして切り出す"""
    chunk = _build_def_chunk(node, lines, nested)
    chunks.append(chunk)
    chunk_source_nodes.append((chunk, [node]))

    for nested_def in _iter_nested_defs(node):
        _collect_def_chunks(nested_def, lines, True, chunks, chunk_source_nodes)

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
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            # トップレベルの関数・クラス。内部にネストされた関数・クラス定義があれば
            # 任意の深さまで再帰的に別Chunkとして切り出す
            _collect_def_chunks(node, lines, False, chunks, chunk_source_nodes)

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

        # entrypoint内(例: if __name__ == "__main__": の中)で定義された関数・クラスも同様に切り出す
        for en in entrypoint_nodes:
            for nested_def in _iter_nested_defs(en):
                _collect_def_chunks(nested_def, lines, True, chunks, chunk_source_nodes)

    # 呼び出し関係の検出（全Chunk名が出揃った後の2パス目。定義順に関係なく解決できる）
    known_names = {c.name for c in chunks}
    for chunk, source_nodes in chunk_source_nodes:
        called = _called_names(source_nodes) & known_names
        called.discard(chunk.name)  # 自己再帰は対象外
        chunk.calls = sorted(called)

    return chunks
