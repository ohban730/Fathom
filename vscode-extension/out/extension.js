"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
function activate(context) {
    console.log('DeDoubt VS Code Extension is active.');
    // コマンド登録: dedoubt.startSession
    let disposable = vscode.commands.registerCommand('dedoubt.startSession', async () => {
        let filePath = "";
        // 1. 現在アクティブなエディタからファイルパスを取得
        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document && !editor.document.isUntitled) {
            filePath = editor.document.fileName;
        }
        else {
            // エディタが開いていない場合はファイル選択ダイアログ
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
        // 2. Webview Panel を作成 (エディタ領域中央)
        const panel = vscode.window.createWebviewPanel('dedoubtWebview', `DeDoubt — ${path.basename(filePath)}`, vscode.ViewColumn.One, {
            enableScripts: true,
            retainContextWhenHidden: true
        });
        // 3. Webview HTML のロード
        const htmlPath = path.join(context.extensionPath, 'src', 'webview', 'index.html');
        if (fs.existsSync(htmlPath)) {
            let htmlContent = fs.readFileSync(htmlPath, 'utf8');
            panel.webview.html = htmlContent;
            // HTMLロード後にファイルパスを送信
            setTimeout(() => {
                panel.webview.postMessage({
                    command: 'initSession',
                    filePath: filePath,
                    targetScore: 70
                });
            }, 800);
        }
        else {
            vscode.window.showErrorMessage(`DeDoubt Webview HTML not found: ${htmlPath}`);
        }
    });
    context.subscriptions.push(disposable);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map