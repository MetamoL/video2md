"""YouTube動画をGeminiで解析し、Markdownとして保存するCLIツール。"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
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
PROMPT_EN = """Analyze this video and output Markdown in the following structure. Output only the Markdown body, with no preamble, closing remarks, or code fences. Start headings at ## (do not use #).

## Summary
A summary of the entire video in 10 lines or fewer.

## Visuals
Visual information shown on screen (slides, charts, demos, code, captions, scenery, etc.) as bullet points with [MM:SS] timestamps. Prioritize visual information that does not duplicate the speech.

## Transcript
The full transcript with [MM:SS] timestamps, in the original spoken language. If there are multiple speakers, label them "Speaker A:" etc. Light cleanup of fillers and false starts is fine, but do not omit content."""
PROMPT_DIGEST = """この動画を解析し、以下の構成のMarkdownを出力してください。Markdown本文のみを出力し、前置き・後書き・コードフェンスは不要。見出しは ## から始める（# は使わない）。

## 概要
動画全体の要約を日本語で10行以内。

## 映像・画面の内容
画面に映っている視覚情報（スライド・図表・デモ・コード・テロップ・場面の様子など）を、タイムスタンプ [MM:SS] 付きの箇条書きで日本語で。話し言葉と重複しない視覚情報を優先する。

## 話の流れ
発話内容を、逐語ではなく要点として、タイムスタンプ [MM:SS] 付きの箇条書きで日本語でまとめる。"""
PROMPT_EN_DIGEST = """Analyze this video and output Markdown in the following structure. Output only the Markdown body, with no preamble, closing remarks, or code fences. Start headings at ## (do not use #).

## Summary
A summary of the entire video in 10 lines or fewer.

## Visuals
Visual information shown on screen (slides, charts, demos, code, captions, scenery, etc.) as bullet points with [MM:SS] timestamps. Prioritize visual information that does not duplicate the speech.

## Key points
Summarize the speech as key points (not verbatim), as bullet points with [MM:SS] timestamps."""


class EmptyResponseError(ValueError):
    """Geminiが保存可能な本文を返さなかったことを表す。"""

    def __init__(
        self,
        message: str,
        finish_reason: str | None,
        feedback: dict[str, Any] | None,
    ) -> None:
        self.finish_reason = finish_reason
        self.feedback = feedback
        super().__init__(message)


class GeminiAPIError(Exception):
    """Gemini APIから正常な応答を得られなかったことを表す。"""

    def __init__(self, status: int | None, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(body)


def sanitize_filename(title: str) -> str:
    """タイトルをWindowsでも使える80文字以内のファイル名にする。"""

    cleaned = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", title)
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    cleaned = cleaned[:80].strip().rstrip(".").rstrip()
    cleaned = cleaned or "video"
    # Windowsは「CON」だけでなく「CON.txt」のような拡張子付きも予約扱い
    # （最初のドットまでがデバイス名）。デバイス名の直後に -video を挟む
    cleaned = re.sub(
        r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
        r"\1-video\2",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


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

    youtube_hosts = ("youtube.com", "youtube-nocookie.com")
    if not any(host == domain or host.endswith(f".{domain}") for domain in youtube_hosts):
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    first_part = path_parts[0].lower() if path_parts else ""
    if first_part == "watch":
        values = parse.parse_qs(parsed.query).get("v", [])
        return _valid_video_id(values[0] if values else None)
    if len(path_parts) >= 2 and first_part in {"shorts", "live", "embed", "v"}:
        return _valid_video_id(path_parts[1])
    return None


def canonical_video_url(video_id: str) -> str:
    """Geminiへ渡すYouTube URLを動画IDだけの標準形にする。

    YouTube自身は ``t`` や ``si`` などの共有用クエリを受け付けるが、
    Geminiの ``file_uri`` はそれらを含むURLをHTTP 400で拒否する場合がある。
    動画IDは事前に検証済みなので、解析対象を変えずに付加情報だけを除去する。
    """

    return f"https://www.youtube.com/watch?v={video_id}"


def build_payload(
    url: str,
    extra: str | None,
    lang: str = "ja",
    digest: bool = False,
) -> dict[str, Any]:
    """Gemini generateContent用のリクエスト本文を組み立てる。"""

    if lang == "ja":
        prompt = PROMPT_DIGEST if digest else PROMPT
    elif lang == "en":
        prompt = PROMPT_EN_DIGEST if digest else PROMPT_EN
    else:
        raise ValueError(f"未対応の出力言語です: {lang}")
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


def extract_markdown(resp: dict[str, Any]) -> tuple[str, str]:
    """Gemini応答から本文と終了理由を安全に取り出す。"""

    candidates = resp.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    if not isinstance(candidate, dict):
        candidate = {}
    raw_reason = candidate.get("finishReason")
    finish_reason = raw_reason if isinstance(raw_reason, str) and raw_reason else "STOP"

    raw_feedback = resp.get("promptFeedback")
    feedback = raw_feedback if isinstance(raw_feedback, dict) else None
    content = candidate.get("content")
    parts = content.get("parts", []) if isinstance(content, dict) else []
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and not part.get("thought")
        and isinstance(part.get("text"), str)
    ]
    markdown = "".join(texts).strip()
    if markdown:
        return markdown, finish_reason

    detail = f"finishReason: {finish_reason}"
    if feedback is not None:
        detail += ", promptFeedback: " + json.dumps(feedback, ensure_ascii=False)
    if finish_reason == "RECITATION":
        message = (
            "著作権保護のため逐語の文字起こしが拒否されました。"
            "--digest（要点形式）なら通ることが多いです。"
            f"（{detail}）"
        )
    else:
        message = f"Gemini応答にMarkdown本文がありません（{detail}）"
    raise EmptyResponseError(message, finish_reason, feedback)


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

    def validate(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        key = value.strip()
        if not key:
            return None
        if re.fullmatch(r"[\x21-\x7e]+", key) is None:
            print(
                "APIキーに改行・空白・非ASCII文字が混入しています"
                "（キーの値は表示しません）",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(3)
        return key

    env_value = os.environ.get("GEMINI_API_KEY")
    if env_value is not None:
        key = validate(env_value)
        if key is not None:
            return key

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env_key:
                registry_key, _ = winreg.QueryValueEx(env_key, "GEMINI_API_KEY")
            key = validate(registry_key)
            if key is not None:
                return key
        except (ImportError, OSError):
            pass

    if sys.platform == "win32":
        guidance = 'setx GEMINI_API_KEY "あなたのAPIキー"'
    else:
        guidance = 'export GEMINI_API_KEY="あなたのAPIキー"'
    print(
        f"GEMINI_API_KEY が設定されていません。次のコマンドで設定してください: {guidance}",
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(3)


def _response_body(http_error: error.HTTPError) -> str:
    try:
        body = http_error.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException):
        body = "（応答本文を読み取れませんでした）"
    return body[:2000]


def _retry_notice(message: str) -> None:
    print(f"{message} 20秒後に再試行します…", file=sys.stderr, flush=True)


def call_gemini(
    url: str,
    model: str,
    api_key: str,
    extra: str | None,
    lang: str = "ja",
    digest: bool = False,
) -> tuple[str, str]:
    """Gemini APIを1モード分だけ呼び、本文と終了理由を返す。"""

    try:
        endpoint = f"{API_ROOT}/{parse.quote(model, safe='')}:generateContent"
        data = json.dumps(
            build_payload(url, extra, lang, digest), ensure_ascii=False
        ).encode("utf-8")
        req = request.Request(
            endpoint,
            data=data,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
    except (ValueError, UnicodeEncodeError):
        raise GeminiAPIError(
            None,
            "リクエストの組み立てに失敗しました（APIキーの形式を確認してください）",
        ) from None

    for attempt in range(2):
        try:
            response = request.urlopen(req, timeout=900)
        except error.HTTPError as exc:
            body = _response_body(exc)
            if exc.code in {429, 500, 502, 503, 504} and attempt == 0:
                _retry_notice(f"Gemini APIが一時的に利用できません（HTTP {exc.code}）。")
                time.sleep(20)
                continue
            raise GeminiAPIError(exc.code, body) from exc
        except error.URLError as exc:
            if attempt == 0:
                _retry_notice("Gemini APIへの接続に失敗しました。")
                time.sleep(20)
                continue
            raise GeminiAPIError(None, f"Gemini APIへの接続に失敗しました: {exc.reason}") from exc
        except (TimeoutError, http.client.HTTPException, OSError) as exc:
            # urllibはgetresponse段のOSError（ConnectionResetError等）を
            # URLErrorに変換しないため、ここで受けてtracebackを防ぐ
            raise GeminiAPIError(None, f"Gemini APIとの通信に失敗しました: {exc}") from exc
        except (ValueError, UnicodeEncodeError):
            raise GeminiAPIError(
                None,
                "リクエストの組み立てに失敗しました（APIキーの形式を確認してください）",
            ) from None

        try:
            with response:
                response_bytes = response.read()
        except (TimeoutError, http.client.HTTPException, OSError) as exc:
            raise GeminiAPIError(None, f"Gemini APIの応答読み取りに失敗しました: {exc}") from exc

        try:
            parsed_response = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeminiAPIError(None, f"Gemini APIの応答を解釈できません: {exc}") from exc
        return extract_markdown(parsed_response)

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
    parser.add_argument(
        "--lang",
        choices=["ja", "en"],
        default="ja",
        help="出力言語 / output language",
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="逐語の文字起こしではなく要点を出力 / output key points",
    )
    parser.add_argument("--extra", help="Geminiへの追加指示")
    return parser


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _reconfigure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _show_api_error(exc: GeminiAPIError, prefix: str = "Gemini APIの呼び出しに失敗しました") -> None:
    status = f"HTTP {exc.status}" if exc.status is not None else "通信エラー"
    _stderr(f"{prefix}（{status}）。")
    _stderr(exc.body[:2000])


def _build_document(
    title: str,
    url: str,
    model: str,
    lang: str,
    markdown: str,
    finish_reason: str,
    digest_note: str | None,
) -> str:
    if lang == "en":
        metadata = [
            f"- Source: {url}",
            f"- Date: {dt.date.today().isoformat()}",
            f"- Model: {model}",
        ]
        if digest_note:
            metadata.append(digest_note)
        truncated = (
            f"> ⚠️ This output was truncated (finishReason: {finish_reason})"
        )
    else:
        metadata = [
            f"- 元動画: {url}",
            f"- 取得日: {dt.date.today().isoformat()}",
            f"- モデル: {model}",
        ]
        if digest_note:
            metadata.append(digest_note)
        truncated = (
            f"> ⚠️ この出力は途中で打ち切られています（finishReason: {finish_reason}）"
        )

    document = f"# {title}\n\n" + "\n".join(metadata) + f"\n\n---\n\n{markdown}"
    if finish_reason != "STOP":
        _stderr(f"警告: 出力が途中で打ち切られました（finishReason: {finish_reason}）")
        document += f"\n\n{truncated}"
    return document


def _save_document(
    outdir: Path,
    stem: str,
    video_id: str,
    document: str,
) -> Path | None:
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        output = unique_path(outdir, stem)
        output.write_text(document, encoding="utf-8", newline="\n")
        return output
    except OSError as exc:
        _stderr(f"通常のファイル名で保存できませんでした。代替名で再試行します: {exc}")

    try:
        outdir.mkdir(parents=True, exist_ok=True)
        output = unique_path(outdir, f"video-{video_id}")
        output.write_text(document, encoding="utf-8", newline="\n")
        return output
    except OSError as exc:
        _stderr(f"Markdownの保存に失敗しました: {exc}")
        return None


def _run(argv: list[str] | None) -> int:
    args = _parser().parse_args(argv)
    video_id = extract_video_id(args.url)
    if video_id is None:
        _stderr("エラー: 対応しているYouTube動画のURLを指定してください。")
        return 2
    api_url = canonical_video_url(video_id)

    api_key = get_api_key()
    _stderr("動画タイトルを取得中…")
    title = fetch_video_title(api_url, video_id)
    _stderr("Gemini解析中…（動画が長いと数分かかります）")
    used_digest = args.digest

    try:
        try:
            markdown, finish_reason = call_gemini(
                api_url,
                args.model,
                api_key,
                args.extra,
                args.lang,
                digest=args.digest,
            )
        except EmptyResponseError as exc:
            if args.digest or exc.finish_reason != "RECITATION":
                raise
            _stderr(
                "逐語の文字起こしが拒否されたため、要点形式で自動的に再解析します。"
            )
            markdown, finish_reason = call_gemini(
                api_url,
                args.model,
                api_key,
                args.extra,
                args.lang,
                digest=True,
            )
            used_digest = True
        else:
            if not args.digest and finish_reason == "RECITATION":
                partial_markdown = markdown
                partial_reason = finish_reason
                _stderr(
                    "逐語の文字起こしが一部拒否されたため、要点形式で自動的に再解析します。"
                )
                try:
                    markdown, finish_reason = call_gemini(
                        api_url,
                        args.model,
                        api_key,
                        args.extra,
                        args.lang,
                        digest=True,
                    )
                    used_digest = True
                except EmptyResponseError as exc:
                    _stderr(f"要点形式の再解析でも本文を取得できませんでした: {exc}")
                    markdown = partial_markdown
                    finish_reason = partial_reason
                except GeminiAPIError as exc:
                    _show_api_error(exc, "要点形式の再解析に失敗しました")
                    markdown = partial_markdown
                    finish_reason = partial_reason
    except GeminiAPIError as exc:
        _show_api_error(exc)
        return 4
    except EmptyResponseError as exc:
        _stderr(f"Geminiから本文を取得できませんでした: {exc}")
        return 5
    except ValueError as exc:
        _stderr(f"Gemini APIの応答が不正です: {exc}")
        return 5

    digest_note = None
    if used_digest:
        if args.digest:
            digest_note = (
                "- Mode: key points (--digest)"
                if args.lang == "en"
                else "- モード: 要点（--digest指定）"
            )
        else:
            digest_note = (
                "- Mode: key points (verbatim transcript blocked by recitation filter)"
                if args.lang == "en"
                else "- モード: 要点（全文の文字起こしは著作権フィルタにより不可）"
            )

    outdir = args.outdir or Path(__file__).resolve().parent / "out"
    document = _build_document(
        title,
        args.url,
        args.model,
        args.lang,
        markdown,
        finish_reason,
        digest_note,
    )
    output = _save_document(outdir, sanitize_filename(title), video_id, document)
    if output is None:
        sys.stdout.write(document)
        if not document.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        return 1

    resolved_output = output.resolve()
    _stderr(f"保存しました: {resolved_output}")
    print(str(resolved_output), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    _reconfigure_streams()
    try:
        return _run(argv)
    except KeyboardInterrupt:
        _stderr("中断しました")
        return 130


if __name__ == "__main__":
    sys.exit(main())
