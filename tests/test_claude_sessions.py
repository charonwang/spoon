from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spoon.adapters.claude_sessions import (
    ensure_claude_session_id,
    load_claude_sessions,
)
from spoon.commands.init_cmd import create_current_layout
from spoon.paths import project_paths
import subprocess


class ClaudeSessionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo,
                       check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ensure_reuses_same_session_for_run(self):
        first, created = ensure_claude_session_id(self.paths, "run-1")
        self.assertTrue(created)
        second, created_again = ensure_claude_session_id(self.paths, "run-1")
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        self.assertEqual(load_claude_sessions(self.paths)["run-1"], first)

    def test_different_runs_get_different_sessions(self):
        a, _ = ensure_claude_session_id(self.paths, "run-a")
        b, _ = ensure_claude_session_id(self.paths, "run-b")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
