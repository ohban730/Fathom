# CodeLitmus

> **⚠️ Language: Japanese only.** The panel UI, the generated questions, and the grading feedback are all in Japanese. Command names and settings are localized, but everything inside the tool is not. English support is not implemented yet — please treat this as a Japanese-language tool for now.

バイブコーディングによって発生する「理解負債」を、能動学習(質問→回答→採点→フィードバック)によって解消するVS Code拡張機能です。

リトマス試験紙のように、「このコードを自分は本当に理解できているか」を判定します。

## できること

- 開いているPythonファイルをAST解析し、関数/クラス/エントリーポイント単位の**Chunk**に分割
- Chunkごとに理解度を問う質問を生成し、回答を厳格採点。合格するまで再回答ガイドが出る
- 画面下部のPanel領域(TERMINAL等と同じ場所)に**星図(コンステレーションマップ)**として進捗を可視化
- Chunk構造をMermaidフローチャートで表示

## 動作要件

- Python 3.11系（バックエンドの実行に必要。**この拡張機能にPythonランタイムは同梱されていません**）
- (任意) [Ollama](https://ollama.com) — ローカルLLMで採点する場合。未導入時はMockエンジン(固定フィードバック)にフォールバックします

## セットアップ

> **バックエンドサーバーを手動で起動する必要はありません。** 拡張機能が`main.py`(FastAPI)を空きポートで自動起動し、VS Codeを閉じるときに停止します。

### 1. Pythonの依存パッケージをインストール

仮想環境(conda / venvなど)を1つ用意して、以下をインストールします。

```bash
pip install fastapi "uvicorn[standard]" pydantic requests
```

同じ内容の`requirements.txt`が拡張機能のインストール先(`~/.vscode/extensions/`配下)にも同梱されています。

### 2. Python実行体の絶対パスを指定（**必須**）

VS Codeの`settings.json`に、手順1の環境の`python`実行体を指定します。

```json
{
  "codelitmus.pythonPath": "C:\\Users\\<you>\\miniconda3\\envs\\codelitmus\\python.exe"
}
```

未設定だとパネルを開いた時点でエラーになります。**つまずくポイントはほぼここです。**

### 3. (任意) Ollamaでモデルを取得

```bash
ollama pull qwen2.5-coder:7b
```

モデル名は固定されていません。pull済みのモデルから選んで使えます（→「採点に使うモデル」）。未導入のままでもMockエンジンで動作します。

### 4. 実行

Pythonファイルを開いた状態で `Ctrl+Alt+D`（Macは`Cmd+Alt+D`）。エディタで何も開いていない場合はファイル選択ダイアログが開きます。

## 採点に使うモデル

**特定のモデルに固定されてはいません。** パネル右上の「Engine:」バッジの隣に、pull済みOllamaモデルのドロップダウンが表示され、ここで切り替えられます。

- 起動直後はOllamaが返す一覧の**先頭のモデル**が自動選択されます
- Ollama未起動 / pull済みモデルが0件のときはドロップダウンは出ず、`Engine: Mock` になります
- モデルの選択はVS Codeを閉じるとリセットされます
- 採点品質はモデル依存です。7B級以上のコード寄りモデルを推奨します

## ソースから動かす場合

コードを読んだり改造したりしたい場合は、リポジトリをクローンして`vscode-extension/`をVS Codeで開き、`npm install && npm run build` の後に`F5`(Run Extension)でデバッグ実行できます。詳細は[リポジトリのREADME](https://github.com/ohban730/CodeLitmus)を参照してください。

## プライバシー

CodeLitmusはネットワーク的にローカル完結です。コードや回答が外部サーバーへ送られることはありません。

- 通信先は拡張機能が起動するローカルバックエンド(`http://127.0.0.1:<動的ポート>`)と、任意で使うOllama(`localhost:11434`)のみ
- WebviewにはCSP(`default-src 'none'`)を設定し、外部CDN・外部フォントへのアクセスを実行時に遮断しています
- 学習履歴はローカルのSQLite(`codelitmus.db`)にのみ保存されます

唯一の例外は、苦手タグの「🌐 検索」リンクです。これはクリックしたときだけ既定のブラウザでGoogle検索を開きます。

## 対応言語

現状、日本語のみです。

- コマンド名・設定項目の説明は`package.nls.json`で多言語化済み（既定は英語、日本語環境では日本語）
- ただし**パネル内のUI・生成される質問・採点フィードバックはすべて日本語**です。LLMへのプロンプト自体が日本語で書かれているため、出力も日本語で返ります

## ライセンス

MIT License（[LICENSE](LICENSE)）。同梱している第三者ソフトウェアの表記は[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)を参照してください。

Ollamaで使用するモデルのライセンスは、モデルごとに異なります。利用前にご自身でご確認ください。
