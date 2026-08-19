# video2md

YouTube動画URL→Gemini APIで音声+映像を解析→AIに渡せるMarkdownを `out/` に保存する単体CLIツール。正本=`README.ja.md`。

- 実行: `python video2md.py "<YouTubeのURL>"`（APIキー=環境変数 `GEMINI_API_KEY`）
- 規律: `test/` のテストはレビュー側が書く（実装と書き手の分離）＝実装委任時は `test/` 編集禁止。モデル名はAPIが404を返したらエラー文中の新名に追随
