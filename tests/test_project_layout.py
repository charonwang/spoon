import unittest
from pathlib import Path


class ProjectLayoutTests(unittest.TestCase):
    def test_project_uses_src_layout(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertTrue((root / "src" / "spoon" / "__init__.py").exists())
        self.assertFalse((root / "spoon" / "__init__.py").exists())
        self.assertIn('package-dir = {"" = "src"}', pyproject)
        self.assertIn('where = ["src"]', pyproject)
        self.assertIn('include = ["spoon*"]', pyproject)


if __name__ == "__main__":
    unittest.main()
