<!-- codex-environment: 2026-09 -->
# video2md

YouTube URLをGeminiで解析しMarkdownへ保存するPython CLIとMCPサーバー。`video2md.py` が解析・保存、`mcp_server.py` が公開ツール、`md_check.py` が出力検査。インターフェースは README、境界条件は `test/`。

Python 3.12以降の標準ライブラリで実行する設計を保つ。オフライン検証は `python -m unittest discover -s test`。API実行は認証・課金を伴うのでfixture/mocksと区別し、依頼なしに動画を送信しない。既存出力の連番による上書き回避、エラー時の保存、入力URL検証、MCP応答形式を確認する。

環境変数の秘密値を表示・コミットしない。製品が使うGeminiモデルを、この開発環境のAstra設定変更に合わせて書き換えない。
