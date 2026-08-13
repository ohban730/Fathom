"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const net = require("net");
const http = require("http");
const child_process_1 = require("child_process");
function findFreePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.on('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const address = server.address();
            if (address && typeof address === 'object') {
                const port = address.port;
                server.close(() => resolve(port));
            }
            else {
                server.close();
                reject(new Error('空きポートの取得に失敗しました'));
            }
        });
    });
}
function httpGetOk(url) {
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
async function waitUntilHealthy(apiBase, retries = 30, intervalMs = 300) {
    for (let i = 0; i < retries; i++) {
        if (await httpGetOk(`${apiBase}/api/health`)) {
            return true;
        }
        await new Promise((r) => setTimeout(r, intervalMs));
    }
    return false;
}
function httpGetJson(url) {
    return new Promise((resolve, reject) => {
        http.get(url, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                }
                catch (e) {
                    reject(e);
                }
            });
        }).on('error', reject);
    });
}
// main.py(FastAPIバックエンド)をサブプロセスとして起動・監督するクラス。
// ポートは固定せず空きポートを動的に確保することで、他プロセスとの競合を避ける。
class BackendServer {
    constructor(context) {
        this.context = context;
    }
    async start() {
        const pythonPath = vscode.workspace.getConfiguration('codelitmus').get('pythonPath', '');
        if (!pythonPath) {
            vscode.window.showErrorMessage('CodeLitmus: バックエンドを起動できません。設定「codelitmus.pythonPath」にPython実行体の絶対パスを指定してください(セットアップ手順を参照)。');
            return undefined;
        }
        const port = await findFreePort();
        const backendDir = this.context.extensionPath;
        const proc = (0, child_process_1.spawn)(pythonPath, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {
            cwd: backendDir,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });
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
    stop() {
        this.process?.kill();
        this.process = undefined;
        this.apiBase = undefined;
    }
}
class CodeLitmusViewProvider {
    constructor(context, onProgressUpdate) {
        this.context = context;
        this.onProgressUpdate = onProgressUpdate;
        this.isReady = false;
    }
    resolveWebviewView(webviewView) {
        this.view = webviewView;
        this.isReady = false;
        webviewView.webview.options = {
            enableScripts: true
        };
        const htmlPath = path.join(this.context.extensionPath, 'src', 'webview', 'index.html');
        if (fs.existsSync(htmlPath)) {
            webviewView.webview.html = fs.readFileSync(htmlPath, 'utf8');
        }
        else {
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
            }
            else if (message?.command === 'progressUpdate') {
                this.onProgressUpdate(message.fileName, message.current, message.total);
            }
            else if (message?.command === 'showRecentFiles') {
                vscode.commands.executeCommand('codelitmus.showRecentFiles');
            }
            else if (message?.command === 'addFolderToWorkspace') {
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
    setApiBase(apiBase) {
        this.apiBase = apiBase;
        if (this.view && this.isReady) {
            this.view.webview.postMessage({ command: 'backendReady', apiBase });
        }
    }
    postMessage(message) {
        if (this.view && this.isReady) {
            this.view.webview.postMessage(message);
        }
        else {
            // Webviewがまだ準備できていない場合は保留し、readyハンドシェイク後に送信する
            this.pendingMessage = message;
        }
    }
}
CodeLitmusViewProvider.viewType = 'codelitmus.panelView';
function activate(context) {
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
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(CodeLitmusViewProvider.viewType, provider));
    const backend = new BackendServer(context);
    backend.start().then((apiBase) => {
        if (apiBase) {
            provider.setApiBase(apiBase);
        }
    });
    context.subscriptions.push({ dispose: () => backend.stop() });
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
        }
        else {
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
            const projects = json?.data ?? [];
            if (json?.status !== 'success' || projects.length === 0) {
                vscode.window.showInformationMessage('CodeLitmus: まだテストしたファイルの履歴がありません。');
                return;
            }
            const items = projects.map((p) => ({
                label: `$(file) ${path.basename(p.file_path)}`,
                description: p.last_session_at ? new Date(p.last_session_at).toLocaleString() : '',
                detail: p.file_path,
                filePath: p.file_path
            }));
            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: '最近テストしたファイルを選択(フォルダをまたいで一覧表示)',
                matchOnDetail: true
            });
            if (picked) {
                const doc = await vscode.workspace.openTextDocument(picked.filePath);
                await vscode.window.showTextDocument(doc);
            }
        }
        catch (err) {
            vscode.window.showErrorMessage(`CodeLitmus: 最近のファイル取得に失敗しました。${err?.message ?? err}`);
        }
    });
    context.subscriptions.push(showRecentDisposable);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map