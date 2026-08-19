# video2md

YouTube動画URL→Gemini APIで音声+映像を解析→AIに渡せるMarkdownを `out/` に保存する単体CLIツール。正本=`README.md`。

- 実行: `python video2md.py "<YouTubeのURL>"`（キー=環境変数 `GEMINI_API_KEY`・控え=Gドライブ「鍵・秘密情報」）
- 規律: `test/` のテストはClaudeが書く（実装と書き手の分離）。モデル名はAPIが世代交代で404を返したらエラー文中の新名に追随
