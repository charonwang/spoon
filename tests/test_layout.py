from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout
from spoon.commands.prompts_cmd import run as run_prompts
from spoon.commands.run_cmd import run as run_runner
from spoon.layout import LAYOUT_MISSING_MESSAGE, layout_ready
from spoon.paths import project_paths


class LayoutReadyTests(unittest.TestCase):
    def test_layout_ready_false_on_empty_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            self.assertFalse(layout_ready(project_paths(repo)))

    def test_layout_ready_true_after_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)
            self.assertTrue(layout_ready(project_paths(repo)))

    def test_run_without_layout_prints_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = run_runner(Namespace(
                    repo=repo,
                    continue_run=False,
                    label=None,
                    json=False,
                ))
            self.assertEqual(code, 2)
            self.assertIn(LAYOUT_MISSING_MESSAGE, buf.getvalue())

    def test_prompts_without_layout_prints_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = run_prompts(Namespace(repo=repo))
            self.assertEqual(code, 2)
            self.assertIn(LAYOUT_MISSING_MESSAGE, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
