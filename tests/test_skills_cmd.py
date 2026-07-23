from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from spoon.commands.skills_cmd import run_status
from spoon.skills_install import (
    SKILL_DIR_NAME,
    bundled_skill_dir,
    install_skill_symlink,
    install_user_skills,
)


class SkillsInstallTests(unittest.TestCase):
    def test_bundled_skill_dir_points_at_repo_skill(self):
        source = bundled_skill_dir()
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.name, SKILL_DIR_NAME)
        self.assertTrue((source / "SKILL.md").is_file())

    def test_install_skill_symlink_is_idempotent(self):
        source = bundled_skill_dir()
        self.assertIsNotNone(source)
        assert source is not None
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "skills" / SKILL_DIR_NAME
            first = install_skill_symlink(link, source)
            second = install_skill_symlink(link, source)
            self.assertEqual(first, "installed")
            self.assertEqual(second, "ok")
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), source.resolve())

    def test_install_force_replaces_directory_copy(self):
        source = bundled_skill_dir()
        self.assertIsNotNone(source)
        assert source is not None
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / SKILL_DIR_NAME
            link.mkdir()
            (link / "SKILL.md").write_text("stale\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                install_skill_symlink(link, source, force=False)
            status = install_skill_symlink(link, source, force=True)
            self.assertEqual(status, "installed")
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), source.resolve())

    def test_install_user_skills_writes_requested_targets(self):
        source = bundled_skill_dir()
        self.assertIsNotNone(source)
        assert source is not None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets = [
                root / ".agents" / "skills" / SKILL_DIR_NAME,
                root / ".claude" / "skills" / SKILL_DIR_NAME,
            ]
            results = install_user_skills(source=source, targets=targets)
            self.assertEqual([status for _, status in results], ["installed", "installed"])
            for link in targets:
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), source.resolve())

    def test_skills_status_command_runs(self):
        code = run_status(Namespace())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
