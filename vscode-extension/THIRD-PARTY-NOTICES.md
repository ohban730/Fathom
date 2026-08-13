# サードパーティ ライセンス表記

CodeLitmus本体は MIT License（[LICENSE](LICENSE)）で配布されます。
本ファイルは、配布物に含まれる／実行時に利用する第三者ソフトウェアの著作権表示とライセンスをまとめたものです。

**GPL / LGPL / AGPL 系のコンポーネントは一切含まれていません。**

---

## 1. 配布パッケージ（.vsix）に同梱しているもの

`.vsix`に実体が含まれるため、各ライセンスの表示義務が発生します。ライセンス全文は同梱ファイルを参照してください。
下記のパスは`.vsix`内および`vscode-extension/`配下からの相対パスです。

| コンポーネント | バージョン | ライセンス | 同梱場所 / ライセンス全文 |
|---|---|---|---|
| [Tailwind CSS](https://tailwindcss.com) | `media/vendor/tailwind.VERSION`参照 | MIT | `media/vendor/tailwind.css`（本プロジェクトの`tailwind.config.js`で生成したCSS） / `media/vendor/tailwind.LICENSE.txt` |
| [Mermaid](https://mermaid.js.org) | `media/vendor/mermaid.VERSION`参照 | MIT | `media/vendor/mermaid.min.js` / `media/vendor/mermaid.LICENSE.txt` |
| [Space Grotesk](https://github.com/floriankarsten/space-grotesk) | v22 (latinサブセット) | SIL Open Font License 1.1 | `media/vendor/fonts/SpaceGrotesk-latin.woff2` / `media/vendor/fonts/OFL.txt` |

### Space Grotesk（OFL 1.1）に関する注意

OFL 1.1はフォントファイルを再配布する際、ライセンス全文の同梱を必須としています（同梱済み）。あわせて以下の制約があります。

- フォント単体を有償で販売してはならない（ソフトウェアに同梱しての配布は可）
- 改変版を配布する場合、"Space Grotesk" という Reserved Font Name をそのまま使ってはならない

## 2. ビルド時のみ使用（配布物には含まれない）

`npm install`で開発環境にのみ入るもので、`.vsix`には含まれません。

| コンポーネント | ライセンス |
|---|---|
| TypeScript | Apache-2.0 |
| tailwindcss（CLI） | MIT |
| @types/vscode, @types/node | MIT |

## 3. Pythonバックエンドの依存パッケージ

これらはユーザーが自身の環境に`pip install -r vscode-extension/requirements.txt`でインストールするもので、`.vsix`には同梱していません（配布物ではないため表示義務は発生しませんが、参考として記載します）。

直接依存（`requirements.txt`）:

| パッケージ | ライセンス |
|---|---|
| fastapi | MIT |
| uvicorn（`[standard]`込み） | BSD-3-Clause |
| pydantic | MIT |
| requests | Apache-2.0 |

推移的依存を含めた全27パッケージの内訳:

| ライセンス | パッケージ |
|---|---|
| MIT | fastapi, pydantic, pydantic-core, anyio, h11, httptools, urllib3, charset-normalizer, PyYAML, watchfiles, annotated-types, annotated-doc, typing-inspection, setuptools, wheel, pip |
| BSD-3-Clause | starlette, uvicorn, click, colorama, idna, python-dotenv, websockets |
| Apache-2.0 | requests, packaging（`Apache-2.0 OR BSD-2-Clause`） |
| PSF-2.0 | typing-extensions |
| **MPL-2.0** | **certifi** |

`certifi`のMPL-2.0はファイル単位の弱いコピーレフトです。certifi自身のソースを改変して配布する場合のみ、その改変ファイルの公開義務が生じます。改変せずに利用する分にはCodeLitmus側のライセンスに影響しません。

## 4. Ollama および LLMモデルについて

CodeLitmusは`http://localhost:11434`のOllamaに対してHTTPリクエストを送るだけで、Ollama本体もモデルも同梱していません。

- Ollama本体はMITライセンスで、商用利用を含めライセンス料は発生しません
- **どのモデルをpullして使うかはユーザーの責任です。** モデルごとにライセンスは異なります（例: Llama系はMeta独自のLlama License、Mistral系やQwen系はApache-2.0が多い、GemmaはGoogle独自の利用規約）。利用前に各モデルのライセンスをご確認ください
