import tempfile
import unittest
from pathlib import Path

from spoon.io_util import append_unique_line, read_text, replace_between_markers, write_text
from spoon.paths import find_repo_root, project_paths


class IoAndPathTests(unittest.TestCase):
    def test_write_text_uses_utf8_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "中文.md"
            write_text(path, "a\r\nb\r\n中文")
            self.assertEqual(path.read_bytes(), "a\nb\n中文".encode("utf-8"))
            self.assertEqual(read_text(path), "a\nb\n中文")

    def test_append_unique_line_writes_once_with_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lines.txt"
            append_unique_line(path, "  alpha  ")
            self.assertEqual(path.read_bytes(), b"  alpha\n")
            self.assertEqual(read_text(path), "  alpha\n")
            append_unique_line(path, "alpha")
            append_unique_line(path, "   alpha   ")
            self.assertEqual(path.read_bytes(), b"  alpha\n")
            self.assertEqual(read_text(path), "  alpha\n")

    def test_replace_between_markers_preserves_manual_sections(self):
        original = "top\n<!-- start -->\nold\n<!-- end -->\nbottom\n"
        result = replace_between_markers(original, "<!-- start -->", "<!-- end -->", "new\n")
        self.assertEqual(result, "top\n<!-- start -->\nnew\n<!-- end -->\nbottom\n")

    def test_find_repo_root_finds_git_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            child = repo / "a" / "b"
            child.mkdir(parents=True)
            self.assertEqual(find_repo_root(child), repo)

    def test_project_paths(self):
        repo = Path("D:/repo")
        paths = project_paths(repo)
        self.assertEqual(paths.spoon, repo / ".spoon")
        self.assertEqual(paths.current, repo / ".spoon" / "current")
        self.assertEqual(paths.plan, repo / ".spoon" / "current" / "plan.md")


if __name__ == "__main__":
    unittest.main()
