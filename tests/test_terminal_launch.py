from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.adapters.terminal_launch import (
    build_terminal_argv,
    resolve_launcher_chain,
    resolve_terminal,
    wait_for_exit_file,
    wait_for_nonempty_file,
)
from spoon.io_util import write_text
from spoon.spoon_config import TerminalConfig


class TerminalLaunchTests(unittest.TestCase):
    def test_resolve_launcher_chain_falls_back(self):
        self.assertEqual(
            resolve_launcher_chain(TerminalConfig(
                launcher="windows_terminal")),
            ["windows_terminal", "pwsh", "conhost", "inline"],
        )
        self.assertEqual(
            resolve_launcher_chain(TerminalConfig(launcher="pwsh")),
            ["pwsh", "windows_terminal", "conhost", "inline"],
        )
        self.assertEqual(
            resolve_launcher_chain(TerminalConfig(launcher="inline")),
            ["inline"],
        )
        self.assertEqual(
            resolve_launcher_chain(TerminalConfig(launcher="custom")),
            ["custom"],
        )

    def test_build_windows_terminal_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            inner = ["claude", "--session-id", "abc"]
            with patch(
                "spoon.adapters.terminal_launch.find_executable",
                return_value=r"C:\wt.exe",
            ):
                argv, exe, note = build_terminal_argv(
                    "windows_terminal",
                    cwd=cwd,
                    inner_argv=inner,
                    executable=None,
                    args=None,
                )
            self.assertIsNotNone(argv)
            assert argv is not None
            self.assertEqual(argv[0], r"C:\wt.exe")
            self.assertIn("-d", argv)
            self.assertEqual(argv[-3:], inner)
            self.assertEqual(exe, r"C:\wt.exe")
            self.assertIn("windows_terminal", note)

    def test_build_tabby_argv_has_no_double_dash_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            inner = ["claude", "--session-id", "abc"]
            with patch(
                "spoon.adapters.terminal_launch.find_executable",
                return_value=r"C:\Tabby\Tabby.exe",
            ):
                argv, _exe, note = build_terminal_argv(
                    "tabby",
                    cwd=cwd,
                    inner_argv=inner,
                    executable=None,
                    args=None,
                )
            assert argv is not None
            self.assertEqual(argv[:2], [r"C:\Tabby\Tabby.exe", "run"])
            self.assertEqual(argv[2:], inner)
            self.assertNotIn("--", argv)
            self.assertIn("tabby", note)

    def test_build_pwsh_argv_quotes_inner_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            inner = ["claude", "--name", "Spoon:demo", "do it"]
            with patch(
                "spoon.adapters.terminal_launch.find_executable",
                return_value=r"C:\Program Files\PowerShell\7\pwsh.exe",
            ):
                argv, exe, note = build_terminal_argv(
                    "pwsh",
                    cwd=cwd,
                    inner_argv=inner,
                    executable=None,
                    args=None,
                )
            assert argv is not None
            self.assertEqual(
                argv[0], r"C:\Program Files\PowerShell\7\pwsh.exe")
            self.assertIn("-NoExit", argv)
            self.assertIn("-WorkingDirectory", argv)
            self.assertEqual(
                argv[argv.index("-WorkingDirectory") + 1], str(cwd.resolve()))
            command = argv[argv.index("-Command") + 1]
            self.assertTrue(command.startswith("& "))
            self.assertIn("'claude'", command)
            self.assertIn("'Spoon:demo'", command)
            self.assertIn("'do it'", command)
            self.assertEqual(exe, r"C:\Program Files\PowerShell\7\pwsh.exe")
            self.assertIn("pwsh", note)
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            inner = ["python", "-m", "job"]
            argv, exe, _note = build_terminal_argv(
                "custom",
                cwd=cwd,
                inner_argv=inner,
                executable="tabby",
                args=("{cwd}", "run", "--", "{script}"),
            )
            assert argv is not None
            self.assertEqual(argv[0], "tabby")
            self.assertEqual(argv[1], str(cwd.resolve()))
            self.assertEqual(argv[-1], " ".join(inner))
            self.assertEqual(exe, "tabby")

    def test_resolve_falls_back_when_wt_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            job = cwd / "job.json"

            def _find(name: str):
                return None

            with patch(
                "spoon.adapters.terminal_launch.find_executable",
                side_effect=_find,
            ):
                resolved = resolve_terminal(
                    TerminalConfig(launcher="windows_terminal"),
                    cwd=cwd,
                    job_path=job,
                )
            self.assertIn(resolved.launcher, {"conhost", "inline"})

    def test_wait_for_exit_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            exit_path = Path(tmp) / "exit.txt"
            write_text(exit_path, "0\n")
            self.assertEqual(
                wait_for_exit_file(exit_path, timeout_seconds=2),
                0,
            )

    def test_wait_for_nonempty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.md"
            write_text(path, "# ok\n")
            text = wait_for_nonempty_file(
                path, timeout_seconds=2, stable_seconds=0.2)
            self.assertIn("ok", text)


if __name__ == "__main__":
    unittest.main()
