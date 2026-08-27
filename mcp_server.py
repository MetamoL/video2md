"""video2mdを標準入出力経由で公開するローカルMCPサーバー。"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from typing import Any, Callable

import md_check
import video2md


PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "video2md", "version": "1.0.0"}
TOOL_NAME = "video_to_markdown"

Runner = Callable[[dict[str, Any]], dict[str, Any]]

TOOL = {
    "name": TOOL_NAME,
    "description": "YouTube動画の音声と映像を解析し、Markdownとして保存します。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "解析するYouTube動画のURL",
            },
            "lang": {
                "type": "string",
                "enum": ["ja", "en"],
                "default": "ja",
                "description": "生成する文書の言語",
            },
            "digest": {
                "type": "boolean",
                "default": False,
                "description": "逐語記録ではなく、タイムスタンプ付きの要点を生成する",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(
    request_id: Any,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _validate_arguments(arguments: Any) -> str | None:
    if not isinstance(arguments, dict):
        return "arguments はオブジェクトで指定してください。"
    url = arguments.get("url")
    if not isinstance(url, str) or not url.strip():
        return "YouTube動画のURLを指定してください。"
    if "lang" in arguments and arguments["lang"] not in {"ja", "en"}:
        return "lang は ja または en を指定してください。"
    if "digest" in arguments and not isinstance(arguments["digest"], bool):
        return "digest は真偽値で指定してください。"
    unknown = set(arguments) - {"url", "lang", "digest"}
    if unknown:
        return f"未対応の引数です: {', '.join(sorted(unknown))}"
    return None


def _format_tool_result(output: dict[str, Any]) -> str:
    markdown = output.get("markdown")
    file_path = output.get("file_path")
    warnings = output.get("warnings", [])
    if not isinstance(markdown, str) or not isinstance(file_path, str):
        raise ValueError("runnerの戻り値にmarkdownまたはfile_pathがありません")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise ValueError("runnerのwarningsは文字列のリストである必要があります")

    parts = [f"保存先: {file_path}", "", markdown]
    if warnings:
        parts.extend(["", "形式上の警告:", *(f"- {warning}" for warning in warnings)])
    return "\n".join(parts)


def default_runner(arguments: dict[str, Any]) -> dict[str, Any]:
    """既存のvideo2md CLI処理を同一プロセス内で実行する。"""

    validation_error = _validate_arguments(arguments)
    if validation_error:
        raise ValueError(validation_error)

    url = arguments["url"].strip()
    lang = arguments.get("lang", "ja")
    argv = [url, "--lang", lang]
    if arguments.get("digest", False):
        argv.append("--digest")

    captured_stdout = io.StringIO()
    try:
        with redirect_stdout(captured_stdout):
            exit_code = video2md._run(argv)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1

    if exit_code != 0:
        messages = {
            1: "Markdownの保存に失敗しました。",
            2: "対応しているYouTube動画のURLを指定してください。",
            3: "GEMINI_API_KEYが設定されていないか、形式が不正です。",
            4: "Gemini APIまたはネットワークの呼び出しに失敗しました。",
            5: "Geminiから保存できる本文を取得できませんでした。",
            130: "処理が中断されました。",
        }
        raise RuntimeError(messages.get(exit_code, f"video2mdが終了コード{exit_code}で失敗しました。"))

    output_lines = [line.strip() for line in captured_stdout.getvalue().splitlines() if line.strip()]
    if len(output_lines) != 1:
        raise RuntimeError("video2mdから保存先を取得できませんでした。")

    output_path = Path(output_lines[0]).resolve()
    try:
        markdown = output_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"保存したMarkdownを読み取れませんでした: {exc}") from exc

    return {
        "markdown": markdown,
        "file_path": str(output_path),
        "warnings": md_check.check_markdown(markdown, lang),
    }


def handle_request(msg: dict[str, Any], runner: Runner = default_runner) -> dict[str, Any] | None:
    """JSON-RPCリクエストを処理し、通知ならNoneを返す。"""

    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        request_id = msg.get("id") if isinstance(msg, dict) else None
        return _error(request_id, -32600, "Invalid Request")

    if "id" not in msg:
        return None

    request_id = msg["id"]
    method = msg["method"]
    params = msg.get("params", {})

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": [TOOL]})
    if method != "tools/call":
        return _error(request_id, -32601, "Method not found")

    if not isinstance(params, dict) or params.get("name") != TOOL_NAME:
        return _error(request_id, -32602, "Invalid params", "未知のツール名です。")
    arguments = params.get("arguments", {})
    validation_error = _validate_arguments(arguments)
    if validation_error:
        return _response(request_id, _tool_error(validation_error))

    try:
        output = runner(arguments)
        text = _format_tool_result(output)
    except (Exception, SystemExit) as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return _response(request_id, _tool_error(message))

    return _response(
        request_id,
        {"content": [{"type": "text", "text": text}], "isError": False},
    )


def _configure_streams() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main() -> int:
    """改行区切りのJSON-RPCメッセージをstdinから処理する。"""

    _configure_streams()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            try:
                response = handle_request(message)
            except Exception as exc:
                request_id = message.get("id") if isinstance(message, dict) else None
                response = _error(request_id, -32603, "Internal error", str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
