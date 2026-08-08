import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

class DeDoubtViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'dedoubt.panelView';

    private view?: vscode.WebviewView;
    private isReady = false;
    private pendingMessage?: any;

    constructor(private readonly context: vscode.ExtensionContext) {}

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        this.view = webviewView;
        this.isReady = false;

        webviewView.webview.options = {
            enableScripts: true
        };

        const htmlPath = path.join(this.context.extensionPath, 'src', 'webview', 'index.html');
        if (fs.existsSync(htmlPath)) {
            webviewView.webview.html = fs.readFileSync(htmlPath, 'utf8');
        } else {
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
    console.log('DeDoubt VS Code Extension is active.');

    const provider = new DeDoubtViewProvider(context);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(DeDoubtViewProvider.viewType, provider)
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

    // コマンド登録: dedoubt.startSession (Ctrl + Alt + D)
    let disposable = vscode.commands.registerCommand('dedoubt.startSession', async () => {
        let filePath = "";

        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document && !editor.document.isUntitled) {
            filePath = editor.document.fileName;
        } else {
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

export function deactivate() {}
