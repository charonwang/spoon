from __future__ import annotations

import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from spoon.commands.config_cmd import run_ack, run_show
from spoon.commands.init_cmd import create_current_layout
from spoon.config_ack import acknowledge_config, config_ack_status
from spoon.io_util import read_json, write_json_atomic
from spoon.paths import project_paths
from spoon.task_label import conversation_title, sanitize_task_label


class ConfigAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo,
                       check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_needs_confirm_until_ack(self):
        status = config_ack_status(self.paths)
        self.assertTrue(status.needs_confirm)
        acknowledge_config(self.paths)
        status = config_ack_status(self.paths)
        self.assertFalse(status.needs_confirm)

    def test_needs_confirm_after_config_change(self):
        acknowledge_config(self.paths)
        raw = read_json(self.paths.config)
        assert isinstance(raw, dict)
        raw["visible_terminals"] = not bool(raw.get("visible_terminals", False))
        write_json_atomic(self.paths.config, raw)
        status = config_ack_status(self.paths)
        self.assertTrue(status.needs_confirm)
        self.assertIn("changed", status.reason)

    def test_run_show_includes_confirmation_line(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_show(Namespace(repo=self.repo))
        self.assertEqual(code, 0)
        self.assertIn("Confirmation: needed", buf.getvalue())

    def test_run_ack_records(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_ack(Namespace(repo=self.repo))
        self.assertEqual(code, 0)
        self.assertIn("Confirmation: ok", buf.getvalue())
        self.assertFalse(config_ack_status(self.paths).needs_confirm)


class TaskLabelShortTests(unittest.TestCase):
    def test_strips_after_fullwidth_colon(self):
        self.assertEqual(
            sanitize_task_label("万年历网页：按月浏览、选日期、显示农历与节气，可本地打开"),
            "万年历网页",
        )
        self.assertEqual(
            conversation_title("万年历网页：按月浏览、选日期"),
            "Spoon:万年历网页",
        )

    def test_max_len_24(self):
        self.assertEqual(len(sanitize_task_label("x" * 80)), 24)


if __name__ == "__main__":
    unittest.main()
