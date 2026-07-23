from __future__ import annotations

import unittest

from spoon.locale_util import (
    detect_language_tag_from_text,
    detect_task_language_tag,
    language_prompt_instruction,
    normalize_language_tag,
    resolve_language_tag,
)


class LocaleUtilTests(unittest.TestCase):
    def test_normalize_language_tag(self):
        self.assertEqual(normalize_language_tag("zh_CN"), "zh-CN")
        self.assertEqual(normalize_language_tag("ja"), "ja")
        self.assertEqual(normalize_language_tag("en-us"), "en-US")

    def test_detect_chinese_from_brief_prose(self):
        text = "目标是在 README 里增加一段简短的使用说明，方便本地演练。"
        self.assertEqual(detect_language_tag_from_text(text), "zh")

    def test_detect_japanese_from_kana(self):
        text = "このリポジトリはローカル検証用です。短い Usage を追加します。"
        self.assertEqual(detect_language_tag_from_text(text), "ja")

    def test_detect_english_from_prose(self):
        text = (
            "Add a short Usage section to README that explains this local "
            "playground for Spoon multi-tool governance."
        )
        self.assertEqual(detect_language_tag_from_text(text), "en")

    def test_task_language_prefers_brief_over_plan(self):
        brief = "请为 README 增加简短的 Usage 说明。"
        plan = "Add a Usage section to README.md with five lines of English text."
        self.assertEqual(detect_task_language_tag(brief, plan), "zh")

    def test_task_language_defaults_to_english_when_unclear(self):
        self.assertEqual(detect_task_language_tag("", ""), "en")

    def test_resolve_auto_uses_brief(self):
        tag = resolve_language_tag(
            "auto",
            brief_text="请审查计划并给出阻塞项。",
            plan_text="",
        )
        self.assertEqual(tag, "zh")

    def test_resolve_explicit_tag(self):
        self.assertEqual(resolve_language_tag("ja-JP"), "ja-JP")

    def test_language_instruction_mentions_tag(self):
        text = language_prompt_instruction("zh")
        self.assertIn("Task language: zh", text)
        self.assertIn("## Blocking", text)
        self.assertIn("brief.md", text)


if __name__ == "__main__":
    unittest.main()
