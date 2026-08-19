# video2md の仕様テスト（Claude作・実装より先に確定）
# 実行: リポジトリルートで  python -m unittest discover -s test
# ネットワーク・実APIキーは使わない（純粋関数のみ検証）
import os
import sys
import tempfile
import unittest
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

    def test_non_youtube_returns_none(self):
        self.assertIsNone(video2md.extract_video_id("https://example.com/watch?v=x"))


class TestBuildPayload(unittest.TestCase):
    def test_structure(self):
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        payload = video2md.build_payload(url, None)
        parts = payload["contents"][0]["parts"]
        self.assertEqual(parts[0], {"file_data": {"file_uri": url}})
        # 固定プロンプトに主要セクションの指示が入っている
        self.assertIn("文字起こし", parts[1]["text"])
        self.assertIn("映像", parts[1]["text"])
        self.assertIn("概要", parts[1]["text"])

    def test_extra_instruction_appended(self):
        payload = video2md.build_payload(
            "https://www.youtube.com/watch?v=jNQXAC9IVRw", "専門用語は英語のまま"
        )
        self.assertIn("専門用語は英語のまま", payload["contents"][0]["parts"][1]["text"])


class TestExtractMarkdown(unittest.TestCase):
    def test_joins_all_text_parts(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "A"}, {"text": "B"}]}}]}
        self.assertEqual(video2md.extract_markdown(resp), "AB")

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


if __name__ == "__main__":
    unittest.main()
