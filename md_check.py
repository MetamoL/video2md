"""生成されたMarkdownの基本的な形式を検査する。"""

from __future__ import annotations

import re


_BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_UNSAFE_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TIMESTAMP = re.compile(r"\[(?:\d+:)?\d{2}:[0-5]\d\]")


def _has_heading(text: str, heading: str) -> bool:
    return re.search(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", text, re.MULTILINE) is not None


def check_markdown(text: str, lang: str = "ja") -> list[str]:
    """Markdownの形式上の問題を、日本語の警告文字列として返す。"""

    warnings: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["Markdown本文が空です"]

    if _BIDI_CONTROLS.search(text) or _UNSAFE_CONTROLS.search(text):
        warnings.append("表示を崩す可能性がある制御文字が含まれています")

    if not re.search(r"^#[ \t]+\S", text, re.MULTILINE):
        warnings.append("タイトル見出し（# タイトル）が見つかりません")

    if lang == "en":
        required = ("Summary", "Visuals")
        final_headings = ("Transcript", "Key points")
        final_label = "Transcript または Key points"
    else:
        required = ("概要", "映像・画面の内容")
        final_headings = ("文字起こし", "話の流れ")
        final_label = "文字起こし または 話の流れ"

    for heading in required:
        if not _has_heading(text, heading):
            warnings.append(f"「{heading}」の見出しが見つかりません")
    if not any(_has_heading(text, heading) for heading in final_headings):
        warnings.append(f"「{final_label}」の見出しが見つかりません")

    if not _TIMESTAMP.search(text):
        warnings.append("タイムスタンプが見つかりません")

    return warnings
