import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as net from 'net';
import * as http from 'http';
import * as crypto from 'crypto';
import { ChildProcess, spawn } from 'child_process';

// CSPの script-src で使う一回限りのトークン。Webviewを読み込むたびに再生成する。
function createNonce(): string {
    return crypto.randomBytes(16).toString('base64');
}

// LLMが生成する文章(質問・採点フィードバック・自由課題)の出力言語。
// パネルのUI文言自体は日本語固定なので、VS Codeの表示言語(vscode.env.language)には
// あえて追従させず、明示的な設定でのみ切り替える。表示言語に自動追従させると、
// 英語UIでVS Codeを使っている日本語話者の出題が突然英語になってしまうため。
function getOutputLocale(): string {
    return vscode.workspace.getConfiguration('fathom').get<string>('outputLanguage', 'ja');
}

function findFreePort(): Promise<number> {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.on('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const address = server.address();
            if (address && typeof address === 'object') {
                const port = address.port;
                server.close(() => resolve(port));
            } else {
                server.close();
                reject(new Error('空きポートの取得に失敗しました'));
            }
        });
    });
}

function httpGetOk(url: string): Promise<boolean> {
    return new Promise((resolve) => {
        const req = http.get(url, (res) => {
            res.resume();
            resolve(res.statusCode === 200);
        });
        req.on('error', () => resolve(false));
        req.setTimeout(1000, () => {
            req.destroy();
            resolve(false);
        });
    });
}

// バックエンドの起動待ち。初回起動はPython本体の起動とfastapi/uvicornの
// インポートだけで10秒近くかかることがある(低速なディスクやウイルス対策の
// スキャンが挟まる環境では特に)。短く打ち切ると、実際には正常な環境で
// タイムアウト扱いになってしまうため、上限は余裕を持って60秒とする。
// ただし依存パッケージ不足などで即死した場合に60秒待たされては困るので、
// shouldAbort でプロセスの終了を検知したら即座に打ち切る。
async function waitUntilHealthy(
    apiBase: string,
    shouldAbort: () => boolean = () => false,
    retries = 120,
    intervalMs = 500
): Promise<boolean> {
    for (let i = 0; i < retries; i++) {
        if (shouldAbort()) {
            return false;
        }
        if (await httpGetOk(`${apiBase}/api/health`)) {
            return true;
        }
        await new Promise((r) => setTimeout(r, intervalMs));
    }
    return false;
}

function httpGetJson(url: string): Promise<any> {
    return new Promise((resolve, reject) => {
        http.get(url, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch (e) {
                    reject(e);
                }
            });
        }).on('error', reject);
    });
}

// main.py(FastAPIバックエンド)をサブプロセスとして起動・監督するクラス。
// ポートは固定せず空きポートを動的に確保することで、他プロセスとの競合を避ける。
class BackendServer {
    private process: ChildProcess | undefined;
    public apiBase: string | undefined;

    constructor(private readonly context: vscode.ExtensionContext) {}

    async start(): Promise<string | undefined> {
        const pythonPath = vscode.workspace.getConfiguration('fathom').get<string>('pythonPath', '');
        if (!pythonPath) {
            vscode.window.showErrorMessage(
                'Fathom: バックエンドを起動できません。設定「fathom.pythonPath」にPython実行体の絶対パスを指定してください(セットアップ手順を参照)。'
            );
            return undefined;
        }

        const port = await findFreePort();
        const backendDir = this.context.extensionPath;

        // 使用するOllamaモデルは設定で固定できる。バックエンドはVS Code APIを
        // 参照できないため、環境変数として渡す(fathom/llm.py の
        // OLLAMA_MODEL_ENV と対応)。空文字なら未指定=pull済み一覧の先頭が使われる。
        const ollamaModel = vscode.workspace
            .getConfiguration('fathom')
            .get<string>('ollamaModel', '')
            .trim();

        // 学習履歴DBは拡張機能のインストール先ではなくglobalStorageに置く。
        // インストール先はバージョン番号付きのフォルダで、拡張機能を更新すると
        // 古いフォルダごと削除されるため、そこに置くと更新のたびに履歴が消える。
        // globalStorageUriのフォルダはVS Codeが自動作成しないので自分で作る。
        const storageDir = this.context.globalStorageUri.fsPath;
        fs.mkdirSync(storageDir, { recursive: true });
        const dbPath = path.join(storageDir, 'fathom.db');

        const proc = spawn(
            pythonPath,
            ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)],
            {
                cwd: backendDir,
                env: {
                    ...process.env,
                    PYTHONIOENCODING: 'utf-8',
                    FATHOM_OLLAMA_MODEL: ollamaModel,
                    FATHOM_DB_PATH: dbPath
                }
            }
        );
        this.process = proc;

        let stderrTail = '';
        proc.stderr?.on('data', (chunk) => {
            stderrTail = (stderrTail + chunk.toString()).slice(-2000);
        });
        proc.on('error', (err) => {
            vscode.window.showErrorMessage(`Fathom: バックエンドの起動に失敗しました(${pythonPath}): ${err.message}`);
        });
        let exited = false;
        proc.on('exit', (code) => {
            exited = true;
            this.apiBase = undefined;
            if (code !== null && code !== 0) {
                vscode.window.showErrorMessage(`Fathom: バックエンドが異常終了しました(code ${code})。\n${stderrTail}`);
            }
        });

        const apiBase = `http://127.0.0.1:${port}`;
        const healthy = await waitUntilHealthy(apiBase, () => exited);
        if (!healthy) {
            // 即死した場合は exit ハンドラ側が stderr 付きで具体的な原因を出すので、
            // ここで重ねて通知しない(同じ失敗に2つ通知が出ると原因が分かりにくい)。
            if (!exited) {
                const detail = stderrTail.trim()
                    ? `\n\nバックエンドの出力:\n${stderrTail.trim()}`
                    : '';
                vscode.window.showErrorMessage(
                    'Fathom: バックエンドの起動確認がタイムアウトしました(60秒)。' +
                    'fathom.pythonPathの設定と依存パッケージ(fastapi/uvicorn/pydantic/requests)を確認してください。' +
                    detail
                );
            }
            this.stop();
            return undefined;
        }

        this.apiBase = apiBase;
        return apiBase;
    }

    stop(): void {
        this.process?.kill();
        this.process = undefined;
        this.apiBase = undefined;
    }
}

class FathomViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'fathom.panelView';

    private view?: vscode.WebviewView;
    private isReady = false;
    private pendingMessage?: any;
    private apiBase?: string;

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly onProgressUpdate: (fileName: string, current: number, total: number) => void
    ) {}

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        this.view = webviewView;
        this.isReady = false;

        webviewView.webview.options = {
            enableScripts: true,
            // Webviewから読み出せるディスク上の範囲をmedia/配下だけに限定する。
            // Tailwind/Mermaid/フォントはすべて media/vendor/ に同梱してある。
            localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')]
        };

        const htmlPath = path.join(this.context.extensionPath, 'src', 'webview', 'index.html');
        if (fs.existsSync(htmlPath)) {
            webviewView.webview.html = this.buildHtml(webviewView.webview, fs.readFileSync(htmlPath, 'utf8'));
        } else {
            vscode.window.showErrorMessage(`Fathom Webview HTML not found: ${htmlPath}`);
            return;
        }

        // Webview 側の読み込み完了 (ready) を待ってから保留メッセージを送信するハンドシェイク
        webviewView.webview.onDidReceiveMessage((message) => {
            if (message?.command === 'ready') {
                this.isReady = true;
                if (this.apiBase) {
                    webviewView.webview.postMessage({ command: 'backendReady', apiBase: this.apiBase });
                }
                if (this.pendingMessage) {
                    webviewView.webview.postMessage(this.pendingMessage);
                    this.pendingMessage = undefined;
                }
            } else if (message?.command === 'progressUpdate') {
                this.onProgressUpdate(message.fileName, message.current, message.total);
            } else if (message?.command === 'showRecentFiles') {
                vscode.commands.executeCommand('fathom.showRecentFiles');
            } else if (message?.command === 'requestStartSession') {
                // ファイル未選択の案内ビューからの導線。アクティブエディタが無ければ
                // コマンド側がファイル選択ダイアログを開く。
                vscode.commands.executeCommand('fathom.startSession');
            } else if (message?.command === 'addFolderToWorkspace') {
                vscode.commands.executeCommand('workbench.action.addRootFolder');
            }
        });

        webviewView.onDidDispose(() => {
            if (this.view === webviewView) {
                this.view = undefined;
                this.isReady = false;
            }
        });
    }

    // index.html はブラウザで直接開いても崩れないよう素のHTMLとして保守しているので、
    // Webviewへ渡す直前にプレースホルダを実際の値へ差し替える。
    // - ${vendorUri}: media/vendor/ の vscode-webview:// URI(同梱アセットの読み込み元)
    // - ${cspSource}: CSPで許可すべき拡張機能リソースのオリジン
    // - ${nonce}:     このロード限りのscript-src許可トークン
    private buildHtml(webview: vscode.Webview, rawHtml: string): string {
        const vendorUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this.context.extensionUri, 'media', 'vendor')
        );
        const nonce = createNonce();

        return rawHtml
            .replace(/\$\{vendorUri\}/g, vendorUri.toString())
            .replace(/\$\{cspSource\}/g, webview.cspSource)
            .replace(/\$\{nonce\}/g, nonce);
    }

    public setApiBase(apiBase: string): void {
        this.apiBase = apiBase;
        if (this.view && this.isReady) {
            this.view.webview.postMessage({ command: 'backendReady', apiBase, locale: getOutputLocale() });
        }
    }

    // 設定 fathom.outputLanguage の変更をWebviewへ伝える。
    // 反映されるのは以後に生成する質問からで、生成済みの履歴は元の言語のまま残る。
    public notifyLocaleChanged(): void {
        if (this.view && this.isReady) {
            this.view.webview.postMessage({ command: 'localeChanged', locale: getOutputLocale() });
        }
    }

    public postMessage(message: any): void {
        if (this.view && this.isReady) {
            this.view.webview.postMessage(message);
        } else {
            // Webviewがまだ準備できていない場合は保留し、readyハンドシェイク後に送信する
            this.pendingMessage = message;
        }
    }
}

export function activate(context: vscode.ExtensionContext) {
    console.log('Fathom VS Code Extension is active.');

    // 対象ファイル・進捗を表示するステータスバー項目(クリックでパネルを開く)
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = `${FathomViewProvider.viewType}.focus`;
    statusBarItem.text = '$(sparkle) Fathom';
    statusBarItem.tooltip = 'Fathomパネルを開く';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    const provider = new FathomViewProvider(context, (fileName, current, total) => {
        statusBarItem.text = `$(sparkle) Fathom: ${fileName} (${current}/${total})`;
    });
    context.subscriptions.push(
        // retainContextWhenHidden: パネルのタブを切り替えてもWebviewを破棄せず、
        // 星座マップやセッションの進行状況がリセットされないようにする(CLAUDE.mdの規約)。
        vscode.window.registerWebviewViewProvider(FathomViewProvider.viewType, provider, {
            webviewOptions: { retainContextWhenHidden: true }
        })
    );

    const backend = new BackendServer(context);
    backend.start().then((apiBase) => {
        if (apiBase) {
            provider.setApiBase(apiBase);
        }
    });
    context.subscriptions.push({ dispose: () => backend.stop() });

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('fathom.outputLanguage')) {
                provider.notifyLocaleChanged();
            }
        })
    );

    // アクティブエディタ変更イベントの監視（ファイル切り替え時の自動追従）
    vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (editor && editor.document && !editor.document.isUntitled) {
            const filePath = editor.document.fileName;
            if (filePath.endsWith('.py')) {
                provider.postMessage({
                    command: 'switchFile',
                    filePath: filePath,
                    targetScore: 70
                });
            }
        }
    });

    // コマンド登録: fathom.startSession (Ctrl + Alt + D)
    let disposable = vscode.commands.registerCommand('fathom.startSession', async () => {
        let filePath = "";

        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document && !editor.document.isUntitled) {
            filePath = editor.document.fileName;
        } else {
            const uri = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                openLabel: 'Fathom 理解度テストを開始',
                filters: { 'Python Files': ['py'] }
            });
            if (uri && uri.length > 0) {
                filePath = uri[0].fsPath;
            }
        }

        if (!filePath) {
            vscode.window.showWarningMessage('Fathom: テスト対象のファイルが選択されていません。');
            return;
        }

        // パネル領域のFathomビューを表示（未生成なら resolveWebviewView をトリガーする）
        await vscode.commands.executeCommand(`${FathomViewProvider.viewType}.focus`);
        provider.postMessage({
            command: 'initSession',
            filePath: filePath,
            targetScore: 70
        });
    });

    context.subscriptions.push(disposable);

    // コマンド登録: fathom.showRecentFiles (フォルダをまたいだ最近のテスト対象ファイル一覧)
    const showRecentDisposable = vscode.commands.registerCommand('fathom.showRecentFiles', async () => {
        if (!backend.apiBase) {
            vscode.window.showWarningMessage('Fathom: バックエンドがまだ起動していません。');
            return;
        }

        try {
            const json = await httpGetJson(`${backend.apiBase}/api/projects/recent?limit=15`);
            const projects: any[] = json?.data ?? [];
            if (json?.status !== 'success' || projects.length === 0) {
                vscode.window.showInformationMessage('Fathom: まだテストしたファイルの履歴がありません。');
                return;
            }

            const items = projects.map((p) => ({
                label: `$(file) ${path.basename(p.file_path)}`,
                description: p.last_session_at ? new Date(p.last_session_at).toLocaleString() : '',
                detail: p.file_path,
                filePath: p.file_path as string
            }));

            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: '最近テストしたファイルを選択(フォルダをまたいで一覧表示)',
                matchOnDetail: true
            });
            if (picked) {
                const doc = await vscode.workspace.openTextDocument(picked.filePath);
                await vscode.window.showTextDocument(doc);
            }
        } catch (err: any) {
            vscode.window.showErrorMessage(`Fathom: 最近のファイル取得に失敗しました。${err?.message ?? err}`);
        }
    });

    context.subscriptions.push(showRecentDisposable);
}

export function deactivate() {}
