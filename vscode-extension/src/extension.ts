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
    return vscode.workspace.getConfiguration('codelitmus').get<string>('outputLanguage', 'ja');
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

async function waitUntilHealthy(apiBase: string, retries = 30, intervalMs = 300): Promise<boolean> {
    for (let i = 0; i < retries; i++) {
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
        const pythonPath = vscode.workspace.getConfiguration('codelitmus').get<string>('pythonPath', '');
        if (!pythonPath) {
            vscode.window.showErrorMessage(
                'CodeLitmus: バックエンドを起動できません。設定「codelitmus.pythonPath」にPython実行体の絶対パスを指定してください(セットアップ手順を参照)。'
            );
            return undefined;
        }

        const port = await findFreePort();
        const backendDir = this.context.extensionPath;

        const proc = spawn(
            pythonPath,
            ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)],
            {
                cwd: backendDir,
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
            }
        );
        this.process = proc;

        let stderrTail = '';
        proc.stderr?.on('data', (chunk) => {
            stderrTail = (stderrTail + chunk.toString()).slice(-2000);
        });
        proc.on('error', (err) => {
            vscode.window.showErrorMessage(`CodeLitmus: バックエンドの起動に失敗しました(${pythonPath}): ${err.message}`);
        });
        proc.on('exit', (code) => {
            this.apiBase = undefined;
            if (code !== null && code !== 0) {
                vscode.window.showErrorMessage(`CodeLitmus: バックエンドが異常終了しました(code ${code})。\n${stderrTail}`);
            }
        });

        const apiBase = `http://127.0.0.1:${port}`;
        const healthy = await waitUntilHealthy(apiBase);
        if (!healthy) {
            vscode.window.showErrorMessage('CodeLitmus: バックエンドの起動確認がタイムアウトしました。codelitmus.pythonPathの設定と依存パッケージ(fastapi/uvicorn/pydantic/requests)を確認してください。');
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

class CodeLitmusViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'codelitmus.panelView';

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
            vscode.window.showErrorMessage(`CodeLitmus Webview HTML not found: ${htmlPath}`);
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
                vscode.commands.executeCommand('codelitmus.showRecentFiles');
            } else if (message?.command === 'requestStartSession') {
                // ファイル未選択の案内ビューからの導線。アクティブエディタが無ければ
                // コマンド側がファイル選択ダイアログを開く。
                vscode.commands.executeCommand('codelitmus.startSession');
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

    // 設定 codelitmus.outputLanguage の変更をWebviewへ伝える。
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
    console.log('CodeLitmus VS Code Extension is active.');

    // 対象ファイル・進捗を表示するステータスバー項目(クリックでパネルを開く)
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = `${CodeLitmusViewProvider.viewType}.focus`;
    statusBarItem.text = '$(sparkle) CodeLitmus';
    statusBarItem.tooltip = 'CodeLitmusパネルを開く';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    const provider = new CodeLitmusViewProvider(context, (fileName, current, total) => {
        statusBarItem.text = `$(sparkle) CodeLitmus: ${fileName} (${current}/${total})`;
    });
    context.subscriptions.push(
        // retainContextWhenHidden: パネルのタブを切り替えてもWebviewを破棄せず、
        // 星座マップやセッションの進行状況がリセットされないようにする(CLAUDE.mdの規約)。
        vscode.window.registerWebviewViewProvider(CodeLitmusViewProvider.viewType, provider, {
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
            if (e.affectsConfiguration('codelitmus.outputLanguage')) {
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

    // コマンド登録: codelitmus.startSession (Ctrl + Alt + D)
    let disposable = vscode.commands.registerCommand('codelitmus.startSession', async () => {
        let filePath = "";

        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document && !editor.document.isUntitled) {
            filePath = editor.document.fileName;
        } else {
            const uri = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                openLabel: 'CodeLitmus 理解度テストを開始',
                filters: { 'Python Files': ['py'] }
            });
            if (uri && uri.length > 0) {
                filePath = uri[0].fsPath;
            }
        }

        if (!filePath) {
            vscode.window.showWarningMessage('CodeLitmus: テスト対象のファイルが選択されていません。');
            return;
        }

        // パネル領域のCodeLitmusビューを表示（未生成なら resolveWebviewView をトリガーする）
        await vscode.commands.executeCommand(`${CodeLitmusViewProvider.viewType}.focus`);
        provider.postMessage({
            command: 'initSession',
            filePath: filePath,
            targetScore: 70
        });
    });

    context.subscriptions.push(disposable);

    // コマンド登録: codelitmus.showRecentFiles (フォルダをまたいだ最近のテスト対象ファイル一覧)
    const showRecentDisposable = vscode.commands.registerCommand('codelitmus.showRecentFiles', async () => {
        if (!backend.apiBase) {
            vscode.window.showWarningMessage('CodeLitmus: バックエンドがまだ起動していません。');
            return;
        }

        try {
            const json = await httpGetJson(`${backend.apiBase}/api/projects/recent?limit=15`);
            const projects: any[] = json?.data ?? [];
            if (json?.status !== 'success' || projects.length === 0) {
                vscode.window.showInformationMessage('CodeLitmus: まだテストしたファイルの履歴がありません。');
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
            vscode.window.showErrorMessage(`CodeLitmus: 最近のファイル取得に失敗しました。${err?.message ?? err}`);
        }
    });

    context.subscriptions.push(showRecentDisposable);
}

export function deactivate() {}
