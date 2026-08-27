# mcp_server の仕様テスト（Claude作・実装より先に確定）
# 実行: リポジトリルートで  python -m unittest discover -s test
# ネットワーク・実APIキーは使わない（tools/call は差し替え可能な runner に対する検証のみ）
#
# 仕様の骨子:
# - mcp_server.py はローカル型 MCP サーバー（標準入出力・改行区切りの JSON-RPC 2.0）
# - 標準ライブラリのみで実装する（外部SDKを使わない）
# - import しただけでは何も起動しない（`if __name__ == "__main__":` でのみ起動）
# - 中核は純粋関数 mcp_server.handle_request(msg: dict, runner) -> dict | None
#   - runner(arguments: dict) -> {"markdown": str, "file_path": str, "warnings": list[str]}
#     失敗時は例外を送出する。既定の runner は video2md を呼び出す実装（本テストでは使わない）
#   - 通知（id なし）には None を返す＝何も書き出さない
# - APIキー（GEMINI_API_KEY）は tools/call の実行まで要求しない
#   （initialize / tools/list はキー無し環境で成功すること）
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import mcp_server  # noqa: E402


def req(method, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def ok_runner(arguments):
    return {
        "markdown": "# タイトル\n\n## 概要\nテスト",
        "file_path": "C:/tmp/out/タイトル.md",
        "warnings": [],
    }


class TestInitialize(unittest.TestCase):
    def test_initialize_returns_serverinfo_and_tools_capability(self):
        res = mcp_server.handle_request(
            req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}),
            runner=ok_runner,
        )
        self.assertEqual(res["jsonrpc"], "2.0")
        self.assertEqual(res["id"], 1)
        result = res["result"]
        self.assertIsInstance(result["protocolVersion"], str)
        self.assertNotEqual(result["protocolVersion"], "")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "video2md")

    def test_initialized_notification_returns_none(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertIsNone(mcp_server.handle_request(msg, runner=ok_runner))

    def test_ping_returns_empty_result(self):
        res = mcp_server.handle_request(req("ping", id_=7), runner=ok_runner)
        self.assertEqual(res["id"], 7)
        self.assertEqual(res["result"], {})


class TestToolsList(unittest.TestCase):
    def test_lists_single_tool_with_url_required(self):
        res = mcp_server.handle_request(req("tools/list", id_=2), runner=ok_runner)
        tools = res["result"]["tools"]
        self.assertEqual(len(tools), 1)
        tool = tools[0]
        self.assertEqual(tool["name"], "video_to_markdown")
        self.assertIn("description", tool)
        schema = tool["inputSchema"]
        self.assertEqual(schema["type"], "object")
        self.assertIn("url", schema["properties"])
        self.assertEqual(schema["required"], ["url"])
        # 任意引数: lang（ja/en）・digest（真偽値）
        self.assertEqual(set(schema["properties"]["lang"]["enum"]), {"ja", "en"})
        self.assertEqual(schema["properties"]["digest"]["type"], "boolean")


class TestToolsCall(unittest.TestCase):
    def call(self, arguments, runner, id_=3, name="video_to_markdown"):
        return mcp_server.handle_request(
            req("tools/call", {"name": name, "arguments": arguments}, id_=id_),
            runner=runner,
        )

    def test_success_returns_markdown_and_path_as_text(self):
        res = self.call({"url": "https://youtu.be/xxxx"}, ok_runner)
        result = res["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["content"][0]["type"], "text")
        text = result["content"][0]["text"]
        self.assertIn("## 概要", text)
        self.assertIn("タイトル.md", text)

    def test_runner_receives_arguments(self):
        seen = {}

        def spy_runner(arguments):
            seen.update(arguments)
            return ok_runner(arguments)

        self.call({"url": "https://youtu.be/xxxx", "lang": "en", "digest": True}, spy_runner)
        self.assertEqual(seen["url"], "https://youtu.be/xxxx")
        self.assertEqual(seen["lang"], "en")
        self.assertIs(seen["digest"], True)

    def test_warnings_are_included_in_text(self):
        def warn_runner(arguments):
            out = ok_runner(arguments)
            out["warnings"] = ["「概要」の見出しが見つかりません"]
            return out

        res = self.call({"url": "https://youtu.be/xxxx"}, warn_runner)
        text = res["result"]["content"][0]["text"]
        self.assertIn("概要", text)
        self.assertIn("見つかりません", text)

    def test_runner_failure_becomes_isError_result(self):
        def bad_runner(arguments):
            raise RuntimeError("APIキーが未設定です")

        res = self.call({"url": "https://youtu.be/xxxx"}, bad_runner)
        result = res["result"]
        self.assertTrue(result["isError"])
        self.assertIn("APIキー", result["content"][0]["text"])

    def test_missing_url_is_isError_without_calling_runner(self):
        def must_not_run(arguments):
            raise AssertionError("runner must not be called")

        res = self.call({}, must_not_run)
        self.assertTrue(res["result"]["isError"])

    def test_unknown_tool_is_invalid_params_error(self):
        res = self.call({"url": "https://youtu.be/xxxx"}, ok_runner, name="no_such_tool")
        self.assertEqual(res["error"]["code"], -32602)


class TestProtocolErrors(unittest.TestCase):
    def test_unknown_method_is_method_not_found(self):
        res = mcp_server.handle_request(req("no/such", id_=9), runner=ok_runner)
        self.assertEqual(res["error"]["code"], -32601)
        self.assertEqual(res["id"], 9)


class TestStdioSmoke(unittest.TestCase):
    """実プロセスを起動し、改行区切りJSONの往復と正常終了だけを確認する。"""

    def test_initialize_and_tools_list_over_stdio(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
        )
        try:
            lines = (
                json.dumps(req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}))
                + "\n"
                + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
                + json.dumps(req("tools/list", id_=2))
                + "\n"
            )
            out, _err = proc.communicate(lines, timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
        responses = [json.loads(line) for line in out.splitlines() if line.strip()]
        self.assertEqual(len(responses), 2)  # 通知には応答しない
        self.assertEqual(responses[0]["id"], 1)
        self.assertIn("serverInfo", responses[0]["result"])
        self.assertEqual(responses[1]["id"], 2)
        self.assertEqual(
            responses[1]["result"]["tools"][0]["name"], "video_to_markdown"
        )
        self.assertEqual(proc.returncode, 0)  # stdin が閉じたら正常終了


if __name__ == "__main__":
    unittest.main()
