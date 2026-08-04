"""
ASTの基本を理解するためのデモスクリプト
"""
import ast

# ========================================
# 1. シンプルなコードをASTに変換してみる
# ========================================
sample_code = '''
def greet(name):
    message = "こんにちは、" + name
    return message

def add(a, b):
    return a + b
'''

# テキスト → AST に変換
tree = ast.parse(sample_code)

# AST の中身をダンプ（全体像を見る）
print("=" * 60)
print("【1】ASTの全体構造（dump）")
print("=" * 60)
print(ast.dump(tree, indent=2))

# ========================================
# 2. 関数だけを抽出する（DeDoubtのChunk分割に直結）
# ========================================
print("\n" + "=" * 60)
print("【2】関数の一覧を抽出（= Chunk候補）")
print("=" * 60)

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # 関数名
        print(f"\n関数名: {node.name}")
        # 引数
        args = [arg.arg for arg in node.args.args]
        print(f"  引数: {args}")
        # 行番号
        print(f"  開始行: {node.lineno}")
        print(f"  終了行: {node.end_lineno}")

# ========================================
# 3. もう少し複雑なコードで試す
# ========================================
complex_code = '''
import os

class FileProcessor:
    def __init__(self, path):
        self.path = path
    
    def read(self):
        with open(self.path) as f:
            return f.read()
    
    def process(self, data):
        lines = data.split("\\n")
        return [line.strip() for line in lines if line]

def main():
    processor = FileProcessor("test.txt")
    content = processor.read()
    result = processor.process(content)
    print(result)
'''

tree2 = ast.parse(complex_code)

print("\n" + "=" * 60)
print("【3】複雑なコードの構造抽出")
print("=" * 60)

for node in ast.iter_child_nodes(tree2):
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
        print(f"\n[Import] {names}")
    
    elif isinstance(node, ast.ClassDef):
        print(f"\n[クラス] {node.name} (行 {node.lineno}-{node.end_lineno})")
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                args = [arg.arg for arg in item.args.args]
                print(f"  [メソッド] {item.name}({', '.join(args)}) (行 {item.lineno}-{item.end_lineno})")
    
    elif isinstance(node, ast.FunctionDef):
        args = [arg.arg for arg in node.args.args]
        print(f"\n[関数] {node.name}({', '.join(args)}) (行 {node.lineno}-{node.end_lineno})")

# ========================================
# 4. DeDoubtでの使い方のイメージ
# ========================================
print("\n" + "=" * 60)
print("【4】DeDoubt向け: Chunk一覧の生成イメージ")
print("=" * 60)

def extract_chunks(source_code: str) -> list[dict]:
    """ソースコードからChunk（理解の単位）を抽出する"""
    tree = ast.parse(source_code)
    chunks = []
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            chunks.append({
                "type": "function",
                "name": node.name,
                "lines": f"{node.lineno}-{node.end_lineno}",
                "code": ast.get_source_segment(source_code, node),
            })
        elif isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in node.body 
                if isinstance(n, ast.FunctionDef)
            ]
            chunks.append({
                "type": "class",
                "name": node.name,
                "lines": f"{node.lineno}-{node.end_lineno}",
                "methods": methods,
                "code": ast.get_source_segment(source_code, node),
            })
    
    return chunks

chunks = extract_chunks(complex_code)
for i, chunk in enumerate(chunks, 1):
    print(f"\nChunk {i}:")
    print(f"  種別: {chunk['type']}")
    print(f"  名前: {chunk['name']}")
    print(f"  行: {chunk['lines']}")
    if chunk['type'] == 'class':
        print(f"  メソッド: {chunk['methods']}")
    print(f"  コード長: {len(chunk['code'])}文字")
