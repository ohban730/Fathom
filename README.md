# Fathom

バイブコーディングによって発生する「理解負債」を、能動学習(質問→回答→採点→フィードバック)によって解消するVS Code拡張機能。

現在は開発者本人が使う前提のツールです。使いたい人は以下の手順で自分でセットアップしてください(Python/LLM周りの自動インストールは行っていません)。

![FathomのVS Code拡張機能画面 — 学習の星図(コンステレーションマップ)、Mermaid構造フローチャート、Chunk単位の質問と再回答ガイドを表示](docs/screenshots/constellation-map.png)

下部Panel領域(TERMINAL等と同じ場所)に表示される「FATHOM」タブ。関数/クラス単位のChunkが星として配置され、質問への回答・厳格採点・再回答ガイドまでの一連の流れがここで進みます。

## 前提

- Python 3.11系
- (任意) [Ollama](https://ollama.com) — ローカルLLMで採点したい場合。未導入でもMockエンジン(固定フィードバック)で動作します。
- Node.js / npm — **リポジトリをクローンして開発・デバッグ実行する場合のみ**必要です。`.vsix`をインストールして使うだけなら不要です。

## セットアップ手順

利用の仕方によって2通りあります。**共通(手順1〜3)**をやったうえで、**パターンA(ソースからデバッグ実行)** または **パターンB(拡張機能としてインストール)** のどちらかを選んでください。

> **バックエンドサーバーを手動で起動する必要はありません。** 拡張機能が有効化された時点で、`main.py`(FastAPI)を空きポートで自動的にサブプロセス起動し、VS Codeを閉じるときに停止します。Anaconda Promptなどから`uvicorn`を手動で起動しても、拡張機能は自分が起動したポートしか参照しないため使われません(二重起動になります)。

### 【共通1】 Python環境の準備

バックエンド用の仮想環境を1つ用意し、依存パッケージを入れます。**この時点ではリポジトリをクローンしている必要はありません**(パッケージ名を直接指定するため、どのディレクトリで実行しても同じです)。

```bash
conda create -n fathom python=3.11
conda activate fathom
pip install fastapi "uvicorn[standard]" pydantic requests
```

- 環境名は`fathom`でなくても構いません。condaでなくvenvでも構いません
- リポジトリをクローン済みなら、**リポジトリのルート**(`README.md`と`vscode-extension/`が並んでいる階層)で `pip install -r vscode-extension/requirements.txt` としても同じです
- `conda activate`を忘れるとbase環境に入ってしまい、次の手順で指定するPythonからは見えません

**この環境の`python.exe`の絶対パスを後で使う**ので控えておいてください。分からなくなったら、環境に入った状態で以下を実行すると表示されます。

```bash
python -c "import sys; print(sys.executable)"
```

### 【共通2】 (任意) Ollamaのセットアップ

- [ollama.com](https://ollama.com)からインストールし、**好きなモデルを1つ以上**取得する

  ```bash
  ollama pull qwen2.5-coder:7b
  ```

- モデル名は固定されていません。pull済みのモデルの中から選んで使えます(→ [採点に使うモデルを選ぶ](#採点に使うモデルを選ぶ))
- Ollamaが起動していない/モデル未取得の場合、拡張機能は自動的にMockLLMClient(デモ用の固定フィードバック)にフォールバックします。コード内容に応じた厳格な採点をさせたい場合はOllamaが必須です。

### 【共通3】 Python実行体の指定(必須)

拡張機能がバックエンドを起動するために使うPython実行体を、VS Codeの`settings.json`に絶対パスで指定します。

```json
{
  "fathom.pythonPath": "C:\\Users\\<you>\\miniconda3\\envs\\fathom\\python.exe"
}
```

未設定のままだと、パネルを開いた時点で「設定`fathom.pythonPath`にPython実行体の絶対パスを指定してください」というエラーが出ます。**セットアップでつまずくポイントはほぼここです。**

条件は「**その実行体で`fastapi` / `uvicorn` / `pydantic` / `requests`がimportできること**」だけです。拡張機能はこの実行体を直接起動する(`<python.exe> -m uvicorn main:app ...`)ため、condaである必要も、事前に`conda activate`しておく必要も、PATHを通しておく必要もありません。venvの`.venv\Scripts\python.exe`やシステムPythonでも構いません。

---

### パターンA: ソースをクローンしてデバッグ実行する(開発者向け)

コードを読んだり改造したりしたい人向け。VS Codeの拡張機能開発ホスト(Extension Development Host)で動かします。

```bash
git clone https://github.com/ohban730/Fathom.git
cd Fathom/vscode-extension
npm install
npm run build
```

> `npm run build` は Tailwind CSSの生成(`build:css`)とTypeScriptのコンパイル(`compile`)をまとめて実行します。`src/webview/index.html`のクラス名や`tailwind.config.js`を編集したときは、`compile`だけでなく`build`を実行してください。

1. VS Codeで **`vscode-extension/`フォルダ** を開く(リポジトリのルートではなくこのサブフォルダ)
2. `F5`(Run Extension)を押す → 新しいVS Codeウィンドウ(拡張機能開発ホスト)が立ち上がる
3. **その新しいウィンドウのほうで** Pythonファイルを開き、`Ctrl+Alt+D`

`settings.json`の`fathom.pythonPath`は、拡張機能開発ホスト側にも引き継がれるユーザー設定に書いておくのが確実です。

### パターンB: 拡張機能としてインストールして使う(利用者向け)

普通のツールとして使いたい人向け。**Node.js/npmは不要です。**

VS Code拡張機能は**ビルド済みのJavaScript(`out/extension.js`)を同梱した状態で配布**されます。インストール時にあなたのマシンで`npm install`やビルドが走ることはありません。

#### B-1. VS Codeの拡張機能ビューからインストールする

Marketplaceに公開済みであれば、**これが標準の手順**です。ブラウザやコマンドは不要です。

1. VS Codeの左側のアクティビティバーから**拡張機能ビュー**(`Ctrl+Shift+X`)を開く
2. 「Fathom」を検索
3. **「インストール」ボタンを押す** — これだけで完了

#### B-2. `.vsix`ファイルからインストールする(Marketplace未公開時・手動配布時)

```bash
code --install-extension fathom-vscode-<version>.vsix
```

- `.vsix`ファイルは[Releases](https://github.com/ohban730/Fathom/releases)から取得するか、自分でクローンして `npx @vscode/vsce package` で作成します(Marketplaceへの`publish`にはPATが別途必要)
- コマンドを使わず、VS Codeの拡張機能ビュー → 右上「…」→ **「VSIXからのインストール…」** からファイルを選んでも同じです

#### インストール後にやること

**どちらの方法でも、Pythonの依存パッケージだけは自動では入りません。** 【共通1〜3】(pip install / `fathom.pythonPath`設定)を済ませてください。バックエンド本体(`main.py` / `fathom/` / `requirements.txt`)は拡張機能に同梱されているので、別途ダウンロードする必要はありません。

同梱された`requirements.txt`は`~/.vscode/extensions/`配下にあって分かりにくいので、パッケージ名を直接指定しても構いません。

```bash
pip install fastapi "uvicorn[standard]" pydantic requests
```

---

## 使い方

- Pythonファイルを開いた状態で `Ctrl+Alt+D`(Macは`Cmd+Alt+D`)、またはコマンドパレットから「Fathom: 理解度テストを開始」を実行
- 画面下部のPanel領域(TERMINAL等と同じ場所)に「Fathom」タブが表示され、AST解析されたChunk(関数/クラス/エントリーポイント)ごとに質問→回答→採点が進みます
- エディタで何もファイルを開いていない状態で`Ctrl+Alt+D`を押すと、ファイル選択ダイアログが開きます

### 過去にテストしたファイルに戻る(🕒)

パネル右上の**🕒**、またはコマンドパレットの「Fathom: 最近テストしたファイルを開く」で、**過去にテストしたファイルの一覧**(最後にテストした日時の新しい順、最大15件)が出ます。選ぶとそのファイルがエディタで開きます。

- 履歴は絶対パスで記録されているため、**今のワークスペースの外にあるファイルもそのまま開けます**。フォルダを移動して回る必要はありません
- **ファイルが開くところまでが🕒の役割です。** 続けて`Ctrl+Alt+D`を押すとテストが始まります

### 2回目以降 — 過去の学習状態は引き継がれます

同じファイルで再度テストを開始すると、過去の全セッションを横断した記録が反映されます。

- **星図で「取り組み済み」のChunkが区別されます。** その星をクリックすると、そのChunkへ直接ジャンプして解き直せます(初回セッションでは無効)
- **前回つまずいたChunkでは、質問と一緒に「着眼点ガイド」が自動で出ます。** 前回の苦手タグ・フィードバックをもとに、調べるべき検索ワードとLLMに投げるプロンプトが提示されます
- **全Chunkを過去に一度でも合格していれば、質問を解き直さずに完了画面へ直行します。** 同じ問題を繰り返させないためです。改めて解きたい場合は完了画面の「再度理解テストを開始」を押してください
- 完了画面には、過去の全セッションを集計した**頻出の苦手タグ**が表示されます

なお、引き継がれるのはChunk単位の合否・苦手タグであり、**「何問目まで進んだか」は保存されません**。途中でパネルを閉じた場合、次回は先頭のChunkから始まります(合格済みのChunkは星図から飛ばして進められます)。

## 採点に使うモデルを選ぶ

**特定のモデルに固定されてはいません。** 決め方は2通りあります。

### 設定で既定モデルを固定する(推奨)

`settings.json`に`fathom.ollamaModel`を書くと、毎回そのモデルで起動します。

```json
{
  "fathom.ollamaModel": "qwen2.5-coder:7b"
}
```

- 指定できるのは`ollama pull`済みのモデル名です(`ollama list`で確認できます)
- `qwen2.5-coder`のようにタグを省略しても、pull済みの`qwen2.5-coder:7b`に補完されます
- **未設定(空文字)の場合は、Ollamaが返す一覧の先頭のモデル**が自動的に選ばれます
- pull済みでない名前を書いた場合も一覧の先頭にフォールバックし、採点機能ごと止まることはありません(どのモデルを使ったかはバックエンドの標準エラー出力に記録されます)
- この設定はバックエンド起動時に読まれます。変更したら**ウィンドウを再読み込み**してください

### パネルのドロップダウンで一時的に切り替える

パネル右上の「Engine:」バッジの隣に、**pull済みモデル一覧のドロップダウン**が表示されます。ここで選び直すと、以降の質問生成・採点にそのモデルが使われます。

- こちらは**その場限りの切り替え**です。VS Codeを閉じると`fathom.ollamaModel`の値(未設定なら一覧の先頭)に戻ります
- Ollamaが未起動、またはpull済みモデルが1つもない場合はドロップダウンは表示されず、`Engine: Mock` になります
- Ollamaを後から起動した場合も、ドロップダウンでモデルを選べば実LLMに切り替わります

採点品質はモデル依存です。小さすぎるモデル(1B〜2B級)ではルーブリック付きJSONを安定して返せないことがあるため、7B級以上のコード寄りモデルを推奨します。

## 別フォルダ・複数フォルダのファイルを対象にする

Fathomはファイルの絶対パスだけで動くため、今開いているワークスペースの外にあるファイルでも制限なく理解度テストできます(パネル右上の「?」アイコンにも同じ内容を表示しています)。

- **1ファイルだけ試す**: `Ctrl+O`で目的のファイルを直接開く。または、エディタで何も開いていない状態で`Ctrl+Alt+D`を押すとファイル選択ダイアログが開き、どこにあるファイルでも選べる。
- **複数フォルダを並べて操作する**: コマンドパレット(`Ctrl+Shift+P`)→ `Workspaces: Add Folder to Workspace...` で、今のリポジトリと無関係な任意のフォルダを追加する。Explorerに複数のフォルダツリーが並び、どちらのファイルをアクティブにしてもFathomは同じ挙動で追従する。共通の親フォルダを1つ開くだけでも同様の効果がある。
- **その組み合わせを保存する**: `File` → `Save Workspace As...` で`.code-workspace`ファイルとして保存すれば、次回からそのファイルを開くだけで同じフォルダ構成を復元できる。

## 学習履歴の保存先

学習履歴(質問・回答・スコア・苦手タグ)はローカルのSQLite `fathom.db` にのみ保存されます。外部には送信されません。

保存先はVS Codeのグローバルストレージです。拡張機能のインストール先はバージョン番号付きのフォルダで、更新のたびに古いフォルダごと削除されるため、そこには置いていません。

| OS | パス |
|---|---|
| Windows | `%APPDATA%\Code\User\globalStorage\fathom.fathom-vscode\fathom.db` |
| macOS | `~/Library/Application Support/Code/User/globalStorage/fathom.fathom-vscode/fathom.db` |
| Linux | `~/.config/Code/User/globalStorage/fathom.fathom-vscode/fathom.db` |

- DBファイルは配布物には含まれておらず、**初回起動時に自動生成**されます(スキーマも自動作成)
- 拡張機能をアンインストールしてもこのファイルは残ります。履歴ごと消したい場合は手動で削除してください
- 別マシンに履歴を持っていきたい場合は、このファイルをコピーするだけで移行できます
- `main.py`を拡張機能を介さず単体で起動した場合のみ、`vscode-extension/fathom.db`(リポジトリ内、gitignore済み)が使われます

## ドキュメント

- [vscode-extension/CHANGELOG.md](vscode-extension/CHANGELOG.md) — バージョンごとの変更履歴(Marketplaceの「Changelog」タブに表示されるもの)
- [docs/data-contract.md](docs/data-contract.md) — Chunkデータが各境界(Python解析層/FastAPI/拡張ホスト/Webview)でどう変わるかのスキーマ契約
- [docs/system_architecture.md](docs/system_architecture.md) — Phase 1(Streamlit MVP)時点の全体アーキテクチャ設計
- [CLAUDE.md](CLAUDE.md) — このリポジトリで開発する際の規約

## 既知の制約

- バックエンドはローカルのPython実行体が前提です。Pythonランタイム自体を同梱した配布は行っていません(自分専用+セットアップ手順公開という方針のため)。
- Ollama未セットアップ時はMockエンジンにフォールバックし、コード内容に応じた厳格な採点にはなりません。
- パネルのドロップダウンでのモデル切り替えは、そのバックエンドプロセスが生きている間だけ有効です。恒久的に決めたい場合は`fathom.ollamaModel`設定を使ってください。

## 対応言語 / Language

**日本語のみです。UI and generated questions are currently Japanese only.**

コマンド名と設定項目の説明のみ`vscode-extension/package.nls.json`（既定=英語）/ `package.nls.ja.json`（日本語）で多言語化しています。パネル内のUI・生成される質問・採点フィードバックは日本語固定です。[`fathom/llm.py`](vscode-extension/fathom/llm.py)のプロンプト自体が日本語で書かれているため、LLMの出力も日本語で返ります。

## ライセンス

Fathom本体は [MIT License](LICENSE) です。

同梱している第三者ソフトウェア(Tailwind CSS / Mermaid / Space Grotesk)と、バックエンドが利用するPythonパッケージのライセンス表記は [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) にまとめています。GPL/LGPL/AGPL系のコンポーネントは含まれていません。

Ollamaで使用するモデルのライセンスはモデルごとに異なります(Llama系はMeta独自ライセンス、Mistral系/Qwen系はApache-2.0が多い、GemmaはGoogle独自の利用規約など)。利用前にご自身でご確認ください。
