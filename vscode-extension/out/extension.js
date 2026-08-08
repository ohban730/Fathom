"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
class DeDoubtViewProvider {
    constructor(context) {
        this.context = context;
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
            vscode.window.showErrorMessage(`DeDoubt Webview HTML not found: ${htmlPath}`);
            return;
        }
        // Webview 側の読み込み完了 (ready) を待ってから保留メッセージを送信するハンドシェイク
        webviewView.webview.onDidReceiveMessage((message) => {
            if (message?.command === 'ready') {
                this.isReady = true;
                if (this.pendingMessage) {
                    webviewView.webview.postMessage(this.pendingMessage);
                    this.pendingMessage = undefined;
                }
            }
        });
        webviewView.onDidDispose(() => {
            if (this.view === webviewView) {
                this.view = undefined;
                this.isReady = false;
            }
        });
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
DeDoubtViewProvider.viewType = 'dedoubt.panelView';
function activate(context) {
    console.log('DeDoubt VS Code Extension is active.');
    const provider = new DeDoubtViewProvider(context);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(DeDoubtViewProvider.viewType, provider));
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
    // コマンド登録: dedoubt.startSession (Ctrl + Alt + D)
    let disposable = vscode.commands.registerCommand('dedoubt.startSession', async () => {
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
                openLabel: 'DeDoubt 理解度テストを開始',
                filters: { 'Python Files': ['py'] }
            });
            if (uri && uri.length > 0) {
                filePath = uri[0].fsPath;
            }
        }
        if (!filePath) {
            vscode.window.showWarningMessage('DeDoubt: テスト対象のファイルが選択されていません。');
            return;
        }
        // パネル領域のDeDoubtビューを表示（未生成なら resolveWebviewView をトリガーする）
        await vscode.commands.executeCommand(`${DeDoubtViewProvider.viewType}.focus`);
        provider.postMessage({
            command: 'initSession',
            filePath: filePath,
            targetScore: 70
        });
    });
    context.subscriptions.push(disposable);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map