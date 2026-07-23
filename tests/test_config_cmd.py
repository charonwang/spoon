from __future__ import annotations

import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from spoon.commands.config_cmd import run_keys, run_show
from spoon.commands.init_cmd import create_current_layout
from spoon.config_report import (
    ToolProbe,
    format_config_keys,
    format_config_show,
    probe_tools,
)
from spoon.spoon_config import AgentsConfig, ClaudeAgentConfig, CodexAgentConfig, SpoonConfig


class ConfigShowTests(unittest.TestCase):
    def test_format_notes_when_claude_enabled_but_missing(self):
        config = SpoonConfig(
            agents=AgentsConfig(
                claude=ClaudeAgentConfig(cli=True, model="m"),
                codex=CodexAgentConfig(cli=False, desktop=False),
            )
        )
        probes = {
            "claude": ToolProbe("Claude Code CLI", "claude", None),
            "codex": ToolProbe("Codex CLI", "codex", None),
        }
        text = format_config_show(config, probes)
        self.assertIn(
            "Claude Code CLI (claude): not installed or not on PATH", text)
        self.assertIn(
            "agents.claude.cli is true, but Claude Code CLI was not found", text)
        self.assertIn(
            "agents.codex.cli and agents.codex.desktop are false", text)

    def test_format_notes_when_codex_desktop_enabled_but_missing(self):
        config = SpoonConfig(
            agents=AgentsConfig(
                claude=ClaudeAgentConfig(cli=False),
                codex=CodexAgentConfig(desktop=True, model="gpt"),
            )
        )
        probes = {
            "claude": ToolProbe("Claude Code CLI", "claude", None),
            "codex": ToolProbe("Codex CLI", "codex", None),
        }
        text = format_config_show(config, probes)
        self.assertIn("Codex CLI (codex): not installed or not on PATH", text)
        self.assertIn("agents.codex.desktop is true", text)
        self.assertIn("not found", text)

    def test_format_notes_when_tools_found(self):
        config = SpoonConfig(
            agents=AgentsConfig(
                claude=ClaudeAgentConfig(cli=True, model="m"),
                codex=CodexAgentConfig(desktop=True, model="gpt"),
            )
        )
        probes = {
            "claude": ToolProbe("Claude Code CLI", "claude", r"C:\bin\claude.exe"),
            "codex": ToolProbe("Codex CLI", "codex", r"C:\bin\codex.exe"),
        }
        text = format_config_show(config, probes)
        self.assertIn("found (C:\\bin\\claude.exe)", text)
        self.assertIn("found (C:\\bin\\codex.exe)", text)
        self.assertIn("via app-server", text)

    @patch("spoon.config_report.find_executable")
    def test_probe_tools_uses_find_executable(self, mock_find):
        mock_find.side_effect = lambda cmd: f"/bin/{cmd}" if cmd == "claude" else None
        probes = probe_tools()
        self.assertTrue(probes["claude"].available)
        self.assertFalse(probes["codex"].available)

    def test_run_show_prints_report(self):
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = run_show(Namespace(repo=repo))
            self.assertEqual(code, 0)
            self.assertIn("Config (.spoon/config.json)", buf.getvalue())
            self.assertIn("Environment", buf.getvalue())
            self.assertIn("terminal:", buf.getvalue())
            self.assertIn("Visible Claude terminal:", buf.getvalue())

    def test_format_config_keys_lists_launchers_and_efforts(self):
        text = format_config_keys()
        self.assertIn("terminal.launcher", text)
        self.assertIn("windows_terminal", text)
        self.assertIn("agents.claude.cli", text)
        self.assertIn("reasoning_effort", text)
        self.assertIn("spoon config show", text)

    def test_run_keys_prints_reference(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_keys(Namespace())
        self.assertEqual(code, 0)
        self.assertIn("Spoon config keys", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
