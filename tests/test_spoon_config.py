import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import write_json_atomic
from spoon.paths import project_paths
from spoon.spoon_config import SpoonConfigError, load_spoon_config


class SpoonConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo,
                       check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_keys_default_false(self):
        write_json_atomic(self.paths.config, {"experimental_cursor_ui": True})
        config = load_spoon_config(self.paths)
        self.assertTrue(config.experimental_cursor_ui)
        self.assertFalse(config.visible_terminals)
        self.assertTrue(config.agents.claude.cli)
        self.assertFalse(config.agents.codex.cli)
        self.assertFalse(config.agents.codex.desktop)
        self.assertEqual(config.language, "auto")
        self.assertEqual(config.agents.codex.project_map, {})

    def test_new_init_defaults(self):
        config = load_spoon_config(self.paths)
        self.assertFalse(config.experimental_cursor_ui)
        self.assertFalse(config.visible_terminals)
        self.assertTrue(config.agents.claude.cli)
        self.assertFalse(config.agents.codex.cli)
        self.assertFalse(config.agents.codex.desktop)
        self.assertEqual(config.language, "auto")
        self.assertEqual(config.agents.codex.project_map, {})
        self.assertEqual(config.terminal.launcher, "windows_terminal")
        self.assertIsNone(config.terminal.executable)
        self.assertIsNone(config.terminal.args)

    def test_terminal_custom_requires_executable_and_args(self):
        write_json_atomic(
            self.paths.config,
            {"terminal": {"launcher": "custom"}},
        )
        with self.assertRaises(SpoonConfigError):
            load_spoon_config(self.paths)

    def test_terminal_config_round_trip(self):
        write_json_atomic(
            self.paths.config,
            {
                "terminal": {
                    "launcher": "tabby",
                    "executable": "C:/Tabby/Tabby.exe",
                    "args": None,
                }
            },
        )
        config = load_spoon_config(self.paths)
        self.assertEqual(config.terminal.launcher, "tabby")
        self.assertEqual(config.terminal.executable, "C:/Tabby/Tabby.exe")

    def test_agents_nested_config(self):
        write_json_atomic(
            self.paths.config,
            {
                "agents": {
                    "claude": {
                        "cli": False,
                        "model": "sonnet",
                    },
                    "codex": {
                        "cli": True,
                        "desktop": True,
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "high",
                        "service_tier": "fast",
                        "project_map": {"a": "b"},
                    },
                    "pi": {"model": "ignored-for-now"},
                },
            },
        )
        config = load_spoon_config(self.paths)
        self.assertFalse(config.agents.claude.cli)
        self.assertEqual(config.agents.claude.model, "sonnet")
        self.assertTrue(config.agents.codex.cli)
        self.assertTrue(config.agents.codex.desktop)
        self.assertEqual(config.agents.codex.model, "gpt-5.6-sol")
        self.assertEqual(config.agents.codex.reasoning_effort, "high")
        self.assertEqual(config.agents.codex.service_tier, "fast")
        self.assertEqual(config.agents.codex.project_map, {"a": "b"})

    def test_removed_flat_keys_raise(self):
        write_json_atomic(
            self.paths.config,
            {
                "claude_cli": False,
                "codex_cli": True,
                "codex_model": "gpt-5.6-sol",
            },
        )
        with self.assertRaises(SpoonConfigError) as ctx:
            load_spoon_config(self.paths)
        self.assertIn("agents", str(ctx.exception))
        self.assertIn("claude_cli", str(ctx.exception))

    def test_language_override(self):
        write_json_atomic(self.paths.config, {"language": "ja-JP"})
        config = load_spoon_config(self.paths)
        self.assertEqual(config.language, "ja-JP")

    def test_invalid_reasoning_effort_raises(self):
        write_json_atomic(
            self.paths.config,
            {"agents": {"codex": {"reasoning_effort": "turbo"}}},
        )
        with self.assertRaises(SpoonConfigError):
            load_spoon_config(self.paths)

    def test_invalid_bool_raises(self):
        write_json_atomic(self.paths.config, {"visible_terminals": "yes"})
        with self.assertRaises(SpoonConfigError):
            load_spoon_config(self.paths)


if __name__ == "__main__":
    unittest.main()
