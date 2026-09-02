# AGENTS.md（Codex用ルーティング）

正本は `CLAUDE.md` と `README.md`（日本語・英語サブ=`README.en.md`）。このリポジトリは単体CLIツール（Python 3.12・標準ライブラリのみ）。

- 動画の内容を参照したいとき: リポジトリルートで `python video2md.py "<YouTubeのURL>"` を実行し、`out/` に生成されたMarkdownを読む
- 実装担当は `test/` 配下を編集しない。受入テスト担当がテストを管理する
- 逐語の文字起こしが拒否される動画は `--digest` を使う。終了コードは 0=成功、1=保存失敗、2=引数またはURL不正、3=APIキー不正、4=APIまたは通信障害、5=モデル拒否、130=中断
