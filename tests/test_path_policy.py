import unittest
from pathlib import Path

from spoon.path_policy import find_bad_plan_links, iter_local_path_tokens, rewrite_local_links_for_export


class PathPolicyTests(unittest.TestCase):
    def test_cursor_file_uri_is_valid_but_bare_paths_are_not(self):
        self.assertEqual(find_bad_plan_links("file:///D:/repo/x.go#L82"), [])
        self.assertEqual(len(find_bad_plan_links(r"D:\repo\x.go:82 D:/repo/y.go:12")), 2)

    def test_export_rewrites_repo_local_uri(self):
        result = rewrite_local_links_for_export(
            "See file:///C:/path/to/your/repo/internal/x.go#L82",
            Path("C:/path/to/your/repo"),
            "demo",
        )
        self.assertIn("repo://demo/internal/x.go#L82", result.text)
        self.assertEqual(iter_local_path_tokens(result.text), [])

    def test_export_redacts_path_outside_repo(self):
        result = rewrite_local_links_for_export(
            r"See C:\Users\example\secret.txt:9",
            Path("C:/path/to/your/repo"),
            "demo",
        )
        self.assertEqual(result.text, "See <local-path>#L9")


if __name__ == "__main__":
    unittest.main()
