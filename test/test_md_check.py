# md_check の仕様テスト（Claude作・実装より先に確定）
# 実行: リポジトリルートで  python -m unittest discover -s test
# ネットワーク・実APIキーは使わない
#
# 仕様: md_check.check_markdown(text: str, lang: str = "ja") -> list[str]
# - 生成されたMarkdownの「形式」だけを検査し、警告文字列のリストを返す（問題なしなら空リスト）
# - 内容の正しさ（要約の質など）は検査しない。壊れた出力を無言で保存しない、が目的
# - 警告は日本語の文字列。検査は標準ライブラリのみで実装する
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import md_check  # noqa: E402


VALID_JA = """# タイトル

- URL: https://youtu.be/xxxx

## 概要
これは概要です。

## 映像・画面の内容
- [00:05] 画面にコードが映る

## 文字起こし
[00:00] こんにちは
[00:12] 本題です
"""

VALID_EN = """# Title

## Summary
Overview here.

## Visuals
- [00:05] Code on screen

## Transcript
[00:00] Hello
"""


class TestValidDocuments(unittest.TestCase):
    def test_valid_ja_returns_no_warnings(self):
        self.assertEqual(md_check.check_markdown(VALID_JA, lang="ja"), [])

    def test_valid_en_returns_no_warnings(self):
        self.assertEqual(md_check.check_markdown(VALID_EN, lang="en"), [])

    def test_default_lang_is_ja(self):
        self.assertEqual(md_check.check_markdown(VALID_JA), [])


class TestMissingParts(unittest.TestCase):
    def test_missing_ja_heading_is_reported(self):
        broken = VALID_JA.replace("## 概要", "## がいよう")
        warnings = md_check.check_markdown(broken, lang="ja")
        self.assertTrue(any("概要" in w for w in warnings), warnings)

    def test_missing_en_heading_is_reported(self):
        broken = VALID_EN.replace("## Transcript", "## Words")
        warnings = md_check.check_markdown(broken, lang="en")
        self.assertTrue(any("Transcript" in w for w in warnings), warnings)

    def test_no_timestamps_is_reported(self):
        no_ts = "\n".join(
            line for line in VALID_JA.splitlines() if "[0" not in line
        )
        warnings = md_check.check_markdown(no_ts, lang="ja")
        self.assertTrue(any("タイムスタンプ" in w for w in warnings), warnings)

    def test_hour_timestamps_are_accepted(self):
        long_video = VALID_JA.replace("[00:12]", "[1:02:33]")
        self.assertEqual(md_check.check_markdown(long_video, lang="ja"), [])


class TestBrokenText(unittest.TestCase):
    def test_empty_text_is_reported(self):
        self.assertNotEqual(md_check.check_markdown("", lang="ja"), [])
        self.assertNotEqual(md_check.check_markdown("   \n", lang="ja"), [])

    def test_bidi_control_chars_are_reported(self):
        # 双方向制御文字が本文に混ざる＝表示崩れの兆候
        warnings = md_check.check_markdown(VALID_JA + "‮怪しい行\n", lang="ja")
        self.assertTrue(any("制御文字" in w for w in warnings), warnings)

    def test_multiple_problems_return_multiple_warnings(self):
        warnings = md_check.check_markdown("ただのテキスト", lang="ja")
        self.assertGreaterEqual(len(warnings), 2)


class TestReturnContract(unittest.TestCase):
    def test_returns_list_of_str_and_does_not_raise(self):
        for text in ["", "# x", VALID_JA, "\x00\x01"]:
            result = md_check.check_markdown(text, lang="ja")
            self.assertIsInstance(result, list)
            for item in result:
                self.assertIsInstance(item, str)


if __name__ == "__main__":
    unittest.main()
