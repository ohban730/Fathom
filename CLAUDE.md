## VS Code Extension Conventions
- The DeDoubt view is a `WebviewViewProvider` registered under `viewsContainers.panel` (the bottom Panel area, alongside Terminal/Output/Debug Console) — see `vscode-extension/package.json`. It must stay there, not move to the sidebar/Activity Bar or become an editor-column `createWebviewPanel`/`ViewColumn` panel.
- Preserve panel state with `retainContextWhenHidden: true` so the constellation map doesn't reset on tab switches.

## No Demo-Specific Logic
Never hardcode behavior keyed to specific demo/sample files (e.g., filename checks, mock scores for `example.py`). All parsing and scoring logic must be generic and work on any file in the workspace. If real data is unavailable, surface an explicit 'no data' state instead of fabricating values.

## Environment
- Always activate the project conda env before running Python: `conda activate dedoubt` (do not create new envs or use base).
- Ask before running `git add -A`; stage only files relevant to the current task and show `git status` first.
- Commit at each verified milestone rather than batching everything into one commit at the end of a session — this keeps rollback points granular and makes bad approaches a `git revert` instead of a manual untangle.

## Python Chunk Parsing
When parsing Python source into chunks, treat `if __name__ == "__main__":` blocks as a first-class chunk (not dead code) and keep chunk boundaries stable across re-parses so star positions in the constellation map don't jump.