# video2md

English: [README.en.md](README.en.md)／紹介記事: [Zenn](https://zenn.dev/metamol/articles/5cdf6a649ed1bc)

YouTube動画をGemini APIで解析し、音声の文字起こしと画面に映る情報を、タイムスタンプ付きのMarkdownとして保存するPython CLIツールです。

Whisper系の文字起こしツールが主に音声を扱うのに対し、video2mdはスライド、図表、コード、デモ、テロップなどの視覚情報も読み取ります。動画を見返すためだけでなく、動画の内容をMarkdownとして検索・引用したり、AIエージェントから参照したりするための変換器です。

ローカルMCPサーバーとしても動作するため、Claude CodeやCodexなどのAIエージェントから動画の内容を直接取得できます。

## 何が出力されるか

通常は、次の3部構成のMarkdownを生成します。

- **概要** — 動画全体の要点を日本語で10行以内に整理します。
- **映像・画面の内容** — スライド、図表、コード、デモ、テロップ、場面の様子などを、`[MM:SS]` 形式のタイムスタンプ付き箇条書きで記録します。発話と重複しない視覚情報を優先します。
- **文字起こし** — 発話全文を元の言語のまま、`[MM:SS]` 形式のタイムスタンプ付きで記録します。複数の話者は「話者A:」のように区別します。

長文の逐語記録が不要な場合は、`--digest` で発話をタイムスタンプ付きの要点にできます。

実際の出力例は [examples/](examples/) を参照してください。

## 必要な環境

- Python 3.12以降
- Gemini APIキー
- 追加のPythonパッケージは不要

APIキーは[Google AI Studio](https://aistudio.google.com/apikey)で取得し、`GEMINI_API_KEY` として設定します。APIの利用にはクォータや料金が発生する場合があります。

Windows PowerShell:

```powershell
setx GEMINI_API_KEY "あなたのAPIキー"
```

`setx` の実行後は、新しいターミナルを開いてください。video2mdは、実行中のプロセスに環境変数が反映されていない場合、Windowsのユーザー環境変数も確認します。

macOSまたはLinux:

```bash
export GEMINI_API_KEY="あなたのAPIキー"
```

## 使い方

リポジトリのルートで、YouTube URLを指定して実行します。

```text
python video2md.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

省略時は `video2md.py` と同じ場所の `out` フォルダーに、動画タイトルを使ったMarkdownファイルを保存します。同名ファイルがある場合は `-2`、`-3` のような番号を付け、既存ファイルを上書きしません。

```text
python video2md.py <URL> [-o OUTDIR] [--model MODEL] [--lang {ja,en}] [--digest] [--extra "追加指示"]
```

| オプション | 既定値 | 説明 |
|---|---|---|
| `-o`, `--outdir` | `out` | Markdownの保存先フォルダー |
| `--model` | `gemini-3.6-flash` | 使用するGeminiモデル。モデル名が更新され、404が返る場合は後述の方法で変更します。 |
| `--lang` | `ja` | 生成する文書の言語。`ja` または `en`。文字起こしはどちらの場合も元の発話言語を維持します。 |
| `--digest` | なし | 逐語の文字起こしではなく、発話をタイムスタンプ付きの要点としてまとめます。 |
| `--extra` | なし | 選択した言語の解析プロンプト末尾に追加する任意の指示です。 |

例:

```powershell
python video2md.py "https://youtu.be/jNQXAC9IVRw" -o notes --model gemini-3.6-flash --lang ja --extra "専門用語は英語のまま記載する"
```

長い動画の解析には数分かかることがあります。Gemini APIの一時的なエラー（HTTP `429`、`500`、`502`、`503`、`504`）や接続失敗が起きた場合は、20秒後に1回だけ再試行します。

Gemini APIへの1回の通信には最大900秒のタイムアウトを設定しています。これは動画自体の長さを900秒に制限するものではありません。

## MCPサーバーとして使う

同梱の `mcp_server.py` をローカル型MCPサーバーとして登録すると、AIエージェントとの会話からvideo2mdを呼び出せます。サーバーが公開するツール名は `video_to_markdown` です。

サーバーのホスティングは不要で、費用が発生し得るのはローカル実行から利用するGemini APIです。長い動画は完了まで数分かかるため、MCPクライアント側のタイムアウトを十分長く設定してください。

### Claude Code

次のパスは、利用者の環境にある `mcp_server.py` の絶対パスへ読み替えてください。

```powershell
claude mcp add video2md -- python C:\path\to\video2md\mcp_server.py
```

### Codex CLIとアプリ

Codex CLI、TUI、IDE拡張、ChatGPTデスクトップアプリは、同じCodexホストのMCP設定を共有します。次のコマンドで登録します。

Windows PowerShell:

```powershell
codex mcp add video2md -- python C:\path\to\video2md\mcp_server.py
```

macOSまたはLinux:

```bash
codex mcp add video2md -- python /absolute/path/to/video2md/mcp_server.py
```

登録後、Codexの設定ファイル（Windowsは `$env:USERPROFILE\.codex\config.toml`、macOSまたはLinuxは `~/.codex/config.toml`）に、登録したサーバーの設定を追加または編集します。APIキーの実値を `--env` や設定ファイルへ書かず、`env_vars` で実行環境から引き継いでください。

Windowsの例:

```toml
[mcp_servers.video2md]
command = "python"
args = ["C:/path/to/video2md/mcp_server.py"]
env_vars = ["GEMINI_API_KEY"]
tool_timeout_sec = 1800
```

macOSまたはLinuxの例:

```toml
[mcp_servers.video2md]
command = "python"
args = ["/absolute/path/to/video2md/mcp_server.py"]
env_vars = ["GEMINI_API_KEY"]
tool_timeout_sec = 1800
```

`tool_timeout_sec` の既定値は60秒ですが、video2mdは長い動画の処理に数分かかり、再試行や要点形式へのフォールバックが重なるとさらに時間がかかることがあります。必要に応じて `1800` を増やしてください。

設定を確認するには、次を実行します。

```text
codex mcp list
```

接続後は、たとえば次のように自然文で依頼できます。

```text
この動画の内容を踏まえて、要点を日本語で説明して https://youtu.be/VIDEO_ID
```

## トラブルシューティング

### RECITATIONで文字起こしを取得できない

長い動画の逐語的な文字起こしは、Geminiから `finishReason: RECITATION` として拒否されることがあります。この場合は要点形式で1回だけ自動的に再解析します。最初から要点形式を使うには `--digest` を指定します。

```powershell
python video2md.py "https://youtu.be/VIDEO_ID" --digest
```

### モデルのHTTP 404エラー

Geminiのモデル名は世代交代で変わることがあります。HTTP 404が返された場合は、APIのエラー文に示された後継モデルを `--model` で指定してください。

```powershell
python video2md.py "https://youtu.be/VIDEO_ID" --model NEW_MODEL_NAME
```

### 標準出力と終了コード

終了コード0では、標準出力に保存先の絶対パスを1行だけ出します。進捗、再試行通知、警告、エラーはすべて標準エラーへ出します。

終了コード1の保存失敗時だけは、失われないようMarkdown全文を標準出力へ出します。このため、標準出力を保存先パスとして機械的に扱えるのは終了コード0のときだけです。

| コード | 意味 |
|---|---|
| 0 | 成功（警告付き含む）。標準出力は保存先の絶対パス |
| 1 | 保存失敗。標準出力はMarkdown全文 |
| 2 | 引数またはYouTube URLが不正 |
| 3 | APIキーが未設定または形式不正 |
| 4 | Gemini APIまたはネットワークの障害 |
| 5 | RECITATIONなどのモデル拒否により本文を取得できない |
| 130 | ユーザーによる中断 |

## 開発者向け検証

リポジトリルートで次を実行します。

```text
python -m unittest discover -s test -q
```

## 出力例

- [examples/python-in-100-seconds.ja.md](examples/python-in-100-seconds.ja.md) — 画面上のコードを変数名まで読み取った例
- [examples/neural-network-19min.ja.md](examples/neural-network-19min.ja.md) — 19分動画。逐語の文字起こしが拒否され、要点形式へ自動フォールバックした例
- [examples/me-at-the-zoo.ja.md](examples/me-at-the-zoo.ja.md) — YouTube史上最初の動画を変換した実出力

## ライセンス

[MIT](LICENSE)
