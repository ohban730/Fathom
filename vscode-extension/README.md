# CodeLitmus

バイブコーディングによって発生する「理解負債」を、能動学習(質問→回答→採点→フィードバック)によって解消するVS Code拡張機能です。

リトマス試験紙のように、「このコードを自分は本当に理解できているか」を判定します。

## できること

- 開いているPythonファイルをAST解析し、関数/クラス/エントリーポイント単位の**Chunk**に分割
- Chunkごとに理解度を問う質問を生成し、回答を厳格採点。合格するまで再回答ガイドが出る
- 画面下部のPanel領域(TERMINAL等と同じ場所)に**星図(コンステレーションマップ)**として進捗を可視化
- Chunk構造をMermaidフローチャートで表示

## 動作要件

- Python 3.11系（バックエンドの実行に必要）
- (任意) [Ollama](https://ollama.com) — ローカルLLMで採点する場合。未導入時はMockエンジン(固定フィードバック)にフォールバックします

## セットアップ

1. Python環境を用意し、`requirements.txt`をインストール

   ```bash
   pip install -r requirements.txt
   ```

2. VS Codeの`settings.json`にPython実行体の絶対パスを指定（**必須**）

   ```json
   {
     "codelitmus.pythonPath": "C:\\Users\\<you>\\miniconda3\\envs\\codelitmus\\python.exe"
   }
   ```

3. Pythonファイルを開いた状態で `Ctrl+Alt+D`（Macは`Cmd+Alt+D`）

詳細な手順は[リポジトリのREADME](https://github.com/ohban730/CodeLitmus)を参照してください。

## プライバシー

CodeLitmusはネットワーク的にローカル完結です。コードや回答が外部サーバーへ送られることはありません。

- 通信先は拡張機能が起動するローカルバックエンド(`http://127.0.0.1:<動的ポート>`)と、任意で使うOllama(`localhost:11434`)のみ
- WebviewにはCSP(`default-src 'none'`)を設定し、外部CDN・外部フォントへのアクセスを実行時に遮断しています
- 学習履歴はローカルのSQLite(`codelitmus.db`)にのみ保存されます

唯一の例外は、苦手タグの「🌐 検索」リンクです。これはクリックしたときだけ既定のブラウザでGoogle検索を開きます。

## ライセンス

MIT License（[LICENSE](LICENSE)）。同梱している第三者ソフトウェアの表記は[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)を参照してください。

Ollamaで使用するモデルのライセンスは、モデルごとに異なります。利用前にご自身でご確認ください。
