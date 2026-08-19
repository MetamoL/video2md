"""YouTube動画をGeminiで解析し、Markdownとして保存するCLIツール。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib import error, parse, request


DEFAULT_MODEL = "gemini-3.6-flash"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
PROMPT = """この動画を解析し、以下の構成のMarkdownを出力してください。Markdown本文のみを出力し、前置き・後書き・コードフェンスは不要。見出しは ## から始める（# は使わない）。

## 概要
動画全体の要約を日本語で10行以内。

## 映像・画面の内容
画面に映っている視覚情報（スライド・図表・デモ・コード・テロップ・場面の様子など）を、タイムスタンプ [MM:SS] 付きの箇条書きで日本語で。話し言葉と重複しない視覚情報を優先する。

## 文字起こし
発話の全文をタイムスタンプ [MM:SS] 付きで、元の言語のまま書き起こす。話者が複数いる場合は「話者A:」のように区別する。相槌や言い直しは軽く整えてよいが、内容の省略はしない。"""


class GeminiAPIError(Exception):
    """Gemini APIから正常な応答を得られなかったことを表す。"""

    def __init__(self, status: int | None, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(body)


def sanitize_filename(title: str) -> str:
    """タイトルをWindowsでも使える80文字以内のファイル名にする。"""

    cleaned = re.sub(r'[\\/:*?"<>|\t\r\n]', " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    cleaned = cleaned[:80].strip().rstrip(".").rstrip()
    return cleaned or "video"


def _valid_video_id(value: str | None) -> str | None:
    if value and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", value):
        return value
    return None


def extract_video_id(url: str) -> str | None:
    """対応するYouTube URLから動画IDを取り出す。"""

    try:
        parsed = parse.urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return None

    if host == "youtu.be" or host.endswith(".youtu.be"):
        return _valid_video_id(parsed.path.strip("/").split("/", 1)[0])

    if host != "youtube.com" and not host.endswith(".youtube.com"):
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.path.rstrip("/") == "/watch":
        values = parse.parse_qs(parsed.query).get("v", [])
        return _valid_video_id(values[0] if values else None)
    if len(path_parts) >= 2 and path_parts[0] in {"shorts", "live"}:
        return _valid_video_id(path_parts[1])
    return None


def build_payload(url: str, extra: str | None) -> dict[str, Any]:
    """Gemini generateContent用のリクエスト本文を組み立てる。"""

    prompt = PROMPT
    if extra:
        prompt += "\n" + extra
    return {
        "contents": [
            {
                "parts": [
                    {"file_data": {"file_uri": url}},
                    {"text": prompt},
                ]
            }
        ]
    }


def extract_markdown(resp: dict[str, Any]) -> str:
    """Gemini応答内の全テキスト部分を順番どおり連結する。"""

    feedback = resp.get("promptFeedback")
    try:
        candidates = resp["candidates"]
        if not candidates:
            raise KeyError("candidates")
        parts = candidates[0]["content"]["parts"]
        if not parts:
            raise KeyError("parts")
        texts = [part["text"] for part in parts if isinstance(part.get("text"), str)]
        if not texts:
            raise KeyError("text")
        return "".join(texts)
    except (KeyError, IndexError, TypeError):
        detail = ""
        if feedback is not None:
            detail = ": " + json.dumps(feedback, ensure_ascii=False)
        raise ValueError("Gemini応答にMarkdown本文がありません" + detail) from None


def unique_path(outdir: Path, stem: str) -> Path:
    """既存ファイルを上書きしない最初の保存先を返す。"""

    candidate = outdir / f"{stem}.md"
    number = 2
    while candidate.exists():
        candidate = outdir / f"{stem}-{number}.md"
        number += 1
    return candidate


def get_api_key() -> str:
    """環境変数、次いでWindowsのユーザー環境変数からAPIキーを得る。"""

    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env_key:
                registry_key, _ = winreg.QueryValueEx(env_key, "GEMINI_API_KEY")
            if isinstance(registry_key, str) and registry_key:
                return registry_key
        except (ImportError, OSError):
            pass

    print(
        'GEMINI_API_KEY が設定されていません。次のコマンドで設定してください: '
        'setx GEMINI_API_KEY "あなたのAPIキー"',
        file=sys.stderr,
    )
    raise SystemExit(1)


def _response_body(http_error: error.HTTPError) -> str:
    try:
        return http_error.read().decode("utf-8", errors="replace")
    except OSError:
        return "（応答本文を読み取れませんでした）"


def call_gemini(url: str, model: str, api_key: str, extra: str | None) -> str:
    """Gemini APIを呼び、生成されたMarkdownを返す。"""

    endpoint = f"{API_ROOT}/{parse.quote(model, safe='')}:generateContent"
    data = json.dumps(build_payload(url, extra), ensure_ascii=False).encode("utf-8")
    req = request.Request(
        endpoint,
        data=data,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    for attempt in range(2):
        try:
            with request.urlopen(req, timeout=900) as response:
                parsed_response = json.loads(response.read().decode("utf-8"))
            return extract_markdown(parsed_response)
        except error.HTTPError as exc:
            body = _response_body(exc)
            if exc.code in {429, 500, 503} and attempt == 0:
                print(f"Gemini APIが一時的に利用できません（HTTP {exc.code}）。20秒後に再試行します…")
                time.sleep(20)
                continue
            raise GeminiAPIError(exc.code, body) from exc
        except error.URLError as exc:
            raise GeminiAPIError(None, str(exc.reason)) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeminiAPIError(None, f"Gemini APIの応答を解釈できません: {exc}") from exc

    raise AssertionError("到達不能")


def fetch_video_title(url: str, video_id: str | None) -> str:
    """YouTube oEmbedからタイトルを取得し、失敗時は動画IDに戻す。"""

    query = parse.urlencode({"url": url, "format": "json"})
    endpoint = f"https://www.youtube.com/oembed?{query}"
    try:
        with request.urlopen(endpoint, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        title = data.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return video_id or "video"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YouTube動画をGeminiで解析し、Markdownとして保存します。"
    )
    parser.add_argument("url", metavar="URL", help="解析するYouTube動画のURL")
    parser.add_argument("-o", "--outdir", type=Path, help="保存先ディレクトリ")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="使用するGeminiモデル")
    parser.add_argument("--extra", help="Geminiへの追加指示")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    video_id = extract_video_id(args.url)
    if video_id is None:
        print("エラー: 対応しているYouTube動画のURLを指定してください。", file=sys.stderr)
        return 1

    api_key = get_api_key()
    print("動画タイトルを取得中…")
    title = fetch_video_title(args.url, video_id)
    print("Gemini解析中…（動画が長いと数分かかります）")
    try:
        markdown = call_gemini(args.url, args.model, api_key, args.extra)
    except GeminiAPIError as exc:
        status = f"HTTP {exc.status}" if exc.status is not None else "通信エラー"
        print(f"Gemini APIの呼び出しに失敗しました（{status}）。", file=sys.stderr)
        print(exc.body, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Gemini APIの応答が不正です: {exc}", file=sys.stderr)
        return 1

    outdir = args.outdir or Path(__file__).resolve().parent / "out"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        output = unique_path(outdir, sanitize_filename(title))
        document = (
            f"# {title}\n\n"
            f"- 元動画: {args.url}\n"
            f"- 取得日: {dt.date.today().isoformat()}\n"
            f"- モデル: {args.model}\n\n"
            f"---\n\n"
            f"{markdown}"
        )
        output.write_text(document, encoding="utf-8")
    except OSError as exc:
        print(f"Markdownの保存に失敗しました: {exc}", file=sys.stderr)
        return 1

    print(f"保存しました: {output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
