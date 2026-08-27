# video2md

English: [README.en.md](README.en.md)／紹介記事: [Zenn](https://zenn.dev/metamol/articles/5cdf6a649ed1bc)

YouTube動画の音声と映像をGemini APIで解析し、概要、画面内容、文字起こしをMarkdownに保存する単体CLIツールです。
Python 3.12の標準ライブラリだけで動作します。

**Whisper系の文字起こしツールと違い、画面に映る内容（スライド・コード・数式・グラフ）まで読み取ります。**
実例: [3Blue1Brownの19分動画](examples/neural-network-19min.ja.md)から、アニメーション中の数式やパラメータ数の計算式まで拾えています。

## 前提

- Python 3.12以降
- Gemini APIキー

Windowsでは、APIキーを環境変数 `GEMINI_API_KEY` に設定してください。

```powershell
setx GEMINI_API_KEY "あなたのAPIキー"
```

`setx` の実行後は、新しいターミナルを開いてください。本ツールは未反映の場合にユーザー環境変数も直接確認します。

macOSまたはLinuxでは、次のように設定します。

```bash
export GEMINI_API_KEY="あなたのAPIキー"
```

## 使い方

```powershell
python video2md.py "https://www.youtube.com/watch?v=jNQXAC9IVRw"
```

省略時は `video2md.py` と同じ場所の `out` フォルダーに、動画タイトルを使ったMarkdownファイルを保存します。
同名ファイルがある場合は `-2`、`-3` のような番号を付け、既存ファイルを残します。

```text
python video2md.py <URL> [-o OUTDIR] [--model MODEL] [--lang {ja,en}] [--digest] [--extra "追加指示"]
```

- `-o OUTDIR`: 保存先フォルダーを指定します。
- `--model MODEL`: Geminiモデルを指定します。既定値は `gemini-3.6-flash` です（2026-08時点。APIが「no longer available」を返したら、そのエラー文中の新モデル名に追随します）。
- `--lang {ja,en}`: 出力言語を指定します。`ja` は日本語、`en` は英語で、既定値は `ja` です。文字起こしはどちらでも元の発話言語を維持します。
- `--digest`: 逐語の文字起こしではなく、発話をタイムスタンプ付きの要点としてまとめます。
- `--extra "追加指示"`: 選択された言語の解析用プロンプト末尾に任意の指示を追加します。

例:

```powershell
python video2md.py "https://youtu.be/jNQXAC9IVRw" -o notes --model gemini-3.6-flash --lang ja --extra "専門用語は英語のまま記載する"
```

長い動画の解析には数分かかることがあります。
APIがHTTP 429、500、502、503、504を返した場合と接続に失敗した場合は、20秒後に1回だけ再試行します。
再試行と要点形式への自動フォールバックが重なると、最悪の場合は数十分かかることがあります。

## MCPサーバーとして使う

ローカル型MCPサーバーとして登録すると、AIエージェントとの会話からvideo2mdを直接呼び出せます。
次の `C:\path\to\video2md\mcp_server.py` は、利用者の環境にあるファイルの絶対パスへ読み替えてください。

```powershell
claude mcp add video2md -- python C:\path\to\video2md\mcp_server.py
```

登録後は、会話で「この動画の内容を踏まえて説明して https://youtu.be/VIDEO_ID」のように頼むだけです。
サーバーのホスティングは不要で、費用が発生し得るのはローカル実行から利用するGemini APIだけです。

長い動画は完了まで数分かかるため、MCPクライアント側のタイムアウトを十分長く設定してください（Claude Codeでは環境変数 `MCP_TIMEOUT` を使用します）。

## トラブルシューティング

### RECITATIONで文字起こしを取得できない

長い動画の逐語的な文字起こしは、Geminiから `finishReason: RECITATION` として拒否されることがあります。
この場合は要点形式で1回だけ自動的に再解析します。
最初から要点形式を使うには `--digest` を指定します。

```powershell
python video2md.py "https://youtu.be/VIDEO_ID" --digest
```

### モデルのHTTP 404エラー

Geminiのモデル名は世代交代で変わることがあります。
HTTP 404が返された場合は、APIのエラー文に示された後継モデルを指定してください。

```powershell
python video2md.py "https://youtu.be/VIDEO_ID" --model NEW_MODEL_NAME
```

### 標準出力と終了コード

終了コード0では、標準出力に保存先の絶対パスを1行だけ出します。
進捗、再試行通知、警告、エラーはすべて標準エラーへ出します。
終了コード1の保存失敗時だけは、失われないようMarkdown全文を標準出力へ出します。
このため、標準出力を保存先パスとして機械的に扱えるのは終了コード0のときだけです。

| コード | 意味 |
| --- | --- |
| 0 | 成功（警告付き含む）。標準出力は保存先の絶対パス |
| 1 | 保存失敗。標準出力はMarkdown全文 |
| 2 | 引数またはYouTube URLが不正 |
| 3 | APIキーが未設定または形式不正 |
| 4 | Gemini APIまたはネットワークの障害 |
| 5 | RECITATIONなどのモデル拒否により本文を取得できない |
| 130 | ユーザーによる中断 |

## 出力例

- [examples/python-in-100-seconds.ja.md](examples/python-in-100-seconds.ja.md) — 画面上のコードを変数名まで読み取った例
- [examples/neural-network-19min.ja.md](examples/neural-network-19min.ja.md) — 19分動画。逐語の文字起こしが拒否され、要点形式へ自動フォールバックした例
- [examples/me-at-the-zoo.ja.md](examples/me-at-the-zoo.ja.md) — YouTube史上最初の動画を変換した実出力

## ライセンス

[MIT](LICENSE)
