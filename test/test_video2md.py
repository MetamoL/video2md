# video2md の仕様テスト（Claude作・実装より先に確定）
# 実行: リポジトリルートで  python -m unittest discover -s test
# ネットワーク・実APIキーは使わない（純粋関数と引数検証のみ）
# 仕様の正: 堅牢化改修仕様 v2（2026-08-19 設計レビュー反映済み）
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video2md  # noqa: E402


class TestSanitizeFilename(unittest.TestCase):
    def test_forbidden_chars_replaced_and_collapsed(self):
        # Windows禁止文字 \ / : * ? " < > | は空白化し、連続空白は1つに潰す
        self.assertEqual(
            video2md.sanitize_filename('Q&A: How? "Yes" <ok>|'),
            "Q&A How Yes ok",
        )

    def test_backslash_slash_tab_newline(self):
        self.assertEqual(video2md.sanitize_filename("a\\b/c\td\ne"), "a b c d e")

    def test_empty_becomes_video(self):
        self.assertEqual(video2md.sanitize_filename("   "), "video")
        self.assertEqual(video2md.sanitize_filename('???'), "video")

    def test_max_80_chars(self):
        out = video2md.sanitize_filename("a" * 100)
        self.assertEqual(out, "a" * 80)

    def test_trailing_dots_and_spaces_stripped(self):
        # Windowsはファイル名末尾のドット・空白が不可
        self.assertEqual(video2md.sanitize_filename("name. "), "name")

    def test_control_chars_become_space(self):
        # 制御文字(\x00-\x1f, \x7f)は空白扱い（既存の\t\r\nと同じ）
        self.assertEqual(video2md.sanitize_filename("a\x07b"), "a b")
        self.assertEqual(video2md.sanitize_filename("a\x00b\x7fc"), "a b c")

    def test_bidi_controls_removed(self):
        # 双方向制御文字(U+202A-202E, U+2066-2069)は削除（表示偽装対策）
        self.assertEqual(video2md.sanitize_filename("invoice‮gnp"), "invoicegnp")
        self.assertEqual(video2md.sanitize_filename("a⁦b⁩c"), "abc")

    def test_windows_reserved_names_get_suffix(self):
        # 予約デバイス名（大文字小文字不問・完全一致）は -video を付ける
        self.assertEqual(video2md.sanitize_filename("CON"), "CON-video")
        self.assertEqual(video2md.sanitize_filename("nul"), "nul-video")
        self.assertEqual(video2md.sanitize_filename("com3"), "com3-video")
        self.assertEqual(video2md.sanitize_filename("LPT9"), "LPT9-video")

    def test_reserved_name_lookalikes_untouched(self):
        # 完全一致でないものは変更しない
        self.assertEqual(video2md.sanitize_filename("Console"), "Console")
        self.assertEqual(video2md.sanitize_filename("COM10"), "COM10")

    def test_reserved_name_with_extension_neutralized(self):
        # Windowsは「CON.txt」も予約扱い（最初のドットまでがデバイス名）
        # デバイス名の直後に -video を挟んで無害化する
        self.assertEqual(video2md.sanitize_filename("CON.txt"), "CON-video.txt")
        self.assertEqual(video2md.sanitize_filename("aux.mp4"), "aux-video.mp4")


class TestExtractVideoId(unittest.TestCase):
    def test_watch_url(self):
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube.com/watch?v=jNQXAC9IVRw&t=10s"),
            "jNQXAC9IVRw",
        )

    def test_short_url(self):
        self.assertEqual(
            video2md.extract_video_id("https://youtu.be/jNQXAC9IVRw?si=abc123"),
            "jNQXAC9IVRw",
        )

    def test_shorts_and_live(self):
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube.com/shorts/abcdefghijk"),
            "abcdefghijk",
        )
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube.com/live/abcdefghijk"),
            "abcdefghijk",
        )

    def test_embed_and_v_paths(self):
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube.com/embed/jNQXAC9IVRw"),
            "jNQXAC9IVRw",
        )
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube.com/v/jNQXAC9IVRw"),
            "jNQXAC9IVRw",
        )

    def test_nocookie_domain(self):
        self.assertEqual(
            video2md.extract_video_id("https://www.youtube-nocookie.com/embed/jNQXAC9IVRw"),
            "jNQXAC9IVRw",
        )

    def test_non_youtube_returns_none(self):
        self.assertIsNone(video2md.extract_video_id("https://example.com/watch?v=x"))


class TestBuildPayload(unittest.TestCase):
    URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

    def test_structure(self):
        payload = video2md.build_payload(self.URL, None)
        parts = payload["contents"][0]["parts"]
        self.assertEqual(parts[0], {"file_data": {"file_uri": self.URL}})
        # 固定プロンプトに主要セクションの指示が入っている
        self.assertIn("文字起こし", parts[1]["text"])
        self.assertIn("映像", parts[1]["text"])
        self.assertIn("概要", parts[1]["text"])

    def test_extra_instruction_appended(self):
        payload = video2md.build_payload(self.URL, "専門用語は英語のまま")
        self.assertIn("専門用語は英語のまま", payload["contents"][0]["parts"][1]["text"])

    def test_lang_ja_is_default(self):
        default_text = video2md.build_payload(self.URL, None)["contents"][0]["parts"][1]["text"]
        ja_text = video2md.build_payload(self.URL, None, lang="ja")["contents"][0]["parts"][1]["text"]
        self.assertEqual(default_text, ja_text)

    def test_lang_en_prompt(self):
        payload = video2md.build_payload(self.URL, None, lang="en")
        text = payload["contents"][0]["parts"][1]["text"]
        # 英語プロンプトは英語見出しを指示し、日本語見出しを含まない
        self.assertIn("Summary", text)
        self.assertIn("Visuals", text)
        self.assertIn("Transcript", text)
        self.assertNotIn("概要", text)

    def test_lang_en_with_extra(self):
        payload = video2md.build_payload(self.URL, "Keep jargon as-is", lang="en")
        self.assertIn("Keep jargon as-is", payload["contents"][0]["parts"][1]["text"])

    def test_digest_ja(self):
        # digest=True は「文字起こし」節を「話の流れ」（要点形式）に差し替える
        text = video2md.build_payload(self.URL, None, lang="ja", digest=True)["contents"][0]["parts"][1]["text"]
        self.assertIn("話の流れ", text)
        self.assertIn("要点", text)
        self.assertNotIn("文字起こし", text)
        self.assertIn("概要", text)
        self.assertIn("映像", text)

    def test_digest_en(self):
        text = video2md.build_payload(self.URL, None, lang="en", digest=True)["contents"][0]["parts"][1]["text"]
        self.assertIn("Key points", text)
        self.assertNotIn("Transcript", text)
        self.assertIn("Summary", text)

    def test_digest_default_off_backward_compat(self):
        # digest省略時は従来と同一（後方互換）
        old = video2md.build_payload(self.URL, None, lang="ja")
        new = video2md.build_payload(self.URL, None, lang="ja", digest=False)
        self.assertEqual(old, new)


class TestExtractMarkdown(unittest.TestCase):
    def test_returns_text_and_finish_reason(self):
        resp = {
            "candidates": [
                {"content": {"parts": [{"text": "A"}, {"text": "B"}]}, "finishReason": "STOP"}
            ]
        }
        self.assertEqual(video2md.extract_markdown(resp), ("AB", "STOP"))

    def test_missing_finish_reason_defaults_to_stop(self):
        # finishReason欠落は打ち切り扱いにしない（誤バナー防止）
        resp = {"candidates": [{"content": {"parts": [{"text": "AB"}]}}]}
        self.assertEqual(video2md.extract_markdown(resp), ("AB", "STOP"))

    def test_max_tokens_partial_text_returned_with_reason(self):
        resp = {
            "candidates": [
                {"content": {"parts": [{"text": "partial"}]}, "finishReason": "MAX_TOKENS"}
            ]
        }
        self.assertEqual(video2md.extract_markdown(resp), ("partial", "MAX_TOKENS"))

    def test_thought_parts_excluded(self):
        resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "thinking...", "thought": True}, {"text": "Y"}]
                    },
                    "finishReason": "STOP",
                }
            ]
        }
        self.assertEqual(video2md.extract_markdown(resp), ("Y", "STOP"))

    def test_recitation_empty_content_raises_with_reason_and_hint(self):
        # RECITATION応答の実形: contentキー自体が無い
        resp = {"candidates": [{"finishReason": "RECITATION", "index": 0}]}
        with self.assertRaises(video2md.EmptyResponseError) as cm:
            video2md.extract_markdown(resp)
        self.assertIn("RECITATION", str(cm.exception))
        self.assertIn("--digest", str(cm.exception))
        self.assertEqual(cm.exception.finish_reason, "RECITATION")

    def test_empty_response_error_is_value_error(self):
        # 既存の呼び出し側（except ValueError）を壊さない
        self.assertTrue(issubclass(video2md.EmptyResponseError, ValueError))

    def test_whitespace_only_text_raises(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "  \n "}]}, "finishReason": "STOP"}]}
        with self.assertRaises(ValueError):
            video2md.extract_markdown(resp)

    def test_no_candidates_raises_with_feedback(self):
        resp = {"promptFeedback": {"blockReason": "SAFETY"}}
        with self.assertRaises(ValueError) as cm:
            video2md.extract_markdown(resp)
        self.assertIn("SAFETY", str(cm.exception))

    def test_empty_parts_raises(self):
        resp = {"candidates": [{"content": {"parts": []}}]}
        with self.assertRaises(ValueError):
            video2md.extract_markdown(resp)


class TestUniquePath(unittest.TestCase):
    def test_returns_base_when_free(self):
        with tempfile.TemporaryDirectory() as d:
            p = video2md.unique_path(Path(d), "title")
            self.assertEqual(p, Path(d) / "title.md")

    def test_appends_suffix_when_taken(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "title.md").write_text("x", encoding="utf-8")
            p = video2md.unique_path(Path(d), "title")
            self.assertEqual(p, Path(d) / "title-2.md")
            (Path(d) / "title-2.md").write_text("x", encoding="utf-8")
            p = video2md.unique_path(Path(d), "title")
            self.assertEqual(p, Path(d) / "title-3.md")


class TestGetApiKey(unittest.TestCase):
    def test_env_var_wins(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-key"}):
            self.assertEqual(video2md.get_api_key(), "dummy-key")

    def test_env_var_stripped(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "  dummy-key \n"}):
            self.assertEqual(video2md.get_api_key(), "dummy-key")

    def test_invalid_key_rejected_without_echo(self):
        # 改行入りキーは即エラー（レジストリへフォールバックしない）。
        # キーの値を stderr に出さない（漏洩対策）
        secret = "AQ.fake\nsecret-tail"
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": secret}):
            with redirect_stderr(buf):
                with self.assertRaises(SystemExit) as cm:
                    video2md.get_api_key()
        self.assertEqual(cm.exception.code, 3)
        self.assertNotIn("fake", buf.getvalue())
        self.assertNotIn("secret-tail", buf.getvalue())

    def test_missing_key_exits_3_on_non_windows(self):
        buf = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("sys.platform", "linux"):
                with redirect_stderr(buf):
                    with self.assertRaises(SystemExit) as cm:
                        video2md.get_api_key()
        self.assertEqual(cm.exception.code, 3)
        # 非Windowsではexportを案内（setxではなく）
        self.assertIn("export", buf.getvalue())


class TestCallGeminiExceptionNormalization(unittest.TestCase):
    def test_connection_reset_normalized_to_gemini_api_error(self):
        # urlopen段・読み取り段で素のOSError（ConnectionResetError等）が出ても
        # tracebackで死なず GeminiAPIError に正規化される
        with mock.patch.object(
            video2md.request, "urlopen", side_effect=ConnectionResetError(10054, "reset")
        ):
            with self.assertRaises(video2md.GeminiAPIError):
                video2md.call_gemini(
                    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                    "test-model",
                    "dummy-key",
                    None,
                )


class TestMainArgHandling(unittest.TestCase):
    def test_invalid_url_returns_2(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            rc = video2md.main(["https://example.com/watch?v=x"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
