import unittest

from spoon.task_label import (
    conversation_title,
    extract_task_label_from_brief,
    resolve_task_label,
    sanitize_task_label,
)


class TaskLabelTests(unittest.TestCase):
    def test_extract_goal_first_line(self):
        brief = """# Brief

## Goal

Spoon 冒烟测试：给 README 加 Usage

再写一行应被忽略。

## Non-Goals

- 别的
"""
        self.assertEqual(
            extract_task_label_from_brief(brief),
            "Spoon 冒烟测试",
        )

    def test_sanitize_truncates(self):
        long = "x" * 80
        self.assertEqual(len(sanitize_task_label(long)), 24)

    def test_conversation_title(self):
        self.assertEqual(conversation_title("ST冒烟"), "Spoon:ST冒烟")
        self.assertEqual(conversation_title(""), "Spoon:current")

    def test_resolve_prefers_override(self):
        class _Paths:
            brief = type("P", (), {"is_file": lambda self: False})()

        self.assertEqual(
            resolve_task_label(_Paths(), override="手工标签", existing="旧的"),
            "手工标签",
        )


if __name__ == "__main__":
    unittest.main()
