# video2md

English: [README.md](README.md)

YouTube動画の音声と映像をGemini APIで解析し、概要・画面内容・文字起こしをMarkdownに保存する単体CLIツールです。Python 3.12の標準ライブラリだけで動作します。

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

省略時は `video2md.py` と同じ場所の `out` フォルダーに、動画タイトルを使ったMarkdownファイルを保存します。同名ファイルがある場合は `-2`、`-3` のような番号を付け、既存ファイルを残します。

```text
python video2md.py <URL> [-o OUTDIR] [--model MODEL] [--lang {ja,en}] [--extra "追加指示"]
```

- `-o OUTDIR`: 保存先フォルダーを指定します。
- `--model MODEL`: Geminiモデルを指定します。既定値は `gemini-3.6-flash` です（2026-08時点。APIが「no longer available」を返したら、そのエラー文中の新モデル名に追随します）。
- `--lang {ja,en}`: 出力言語を指定します。`ja` は日本語、`en` は英語で、既定値は `ja` です。文字起こしはどちらでも元の発話言語を維持します。
- `--extra "追加指示"`: 選択された言語の解析用プロンプト末尾に任意の指示を追加します。

例:

```powershell
python video2md.py "https://youtu.be/jNQXAC9IVRw" -o notes --model gemini-3.6-flash --lang ja --extra "専門用語は英語のまま記載する"
```

長い動画の解析には数分かかることがあります。APIがHTTP 429、500、503を返した場合は、20秒後に1回だけ再試行します。

## 出力例

- [examples/python-in-100-seconds.ja.md](examples/python-in-100-seconds.ja.md) — 画面上のコードを変数名まで読み取った例
- [examples/me-at-the-zoo.ja.md](examples/me-at-the-zoo.ja.md) — YouTube史上最初の動画を変換した実出力

## ライセンス

[MIT](LICENSE)
