import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands import archive_cmd
from spoon.commands.archive_cmd import archive_current
from spoon.commands.init_cmd import create_current_layout


class ArchiveCommandTests(unittest.TestCase):
    def test_archive_moves_current_and_recreates_empty_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n", encoding="utf-8")

            dest = archive_current(repo, archive_root, "demo", "task-one", force=False)

            self.assertTrue((dest / "brief.md").exists())
            self.assertTrue((repo / ".spoon" / "current" / "brief.md").exists())
            self.assertEqual((repo / ".spoon" / "current" / "plan.md").read_text(encoding="utf-8"), "")

    def test_archive_refuses_empty_brief_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "brief.md is empty"):
                archive_current(repo, Path(tmp) / "archives", "demo", "empty", force=False)

    def test_archive_refuses_empty_plan_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                archive_current(repo, Path(tmp) / "archives", "demo", "empty-plan", force=False)

    def test_archive_rejects_project_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "project"):
                archive_current(repo, archive_root, "..", "task", force=False)

            self.assertFalse(archive_root.exists())
            self.assertTrue(current.exists())

    def test_archive_rejects_task_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "task"):
                archive_current(repo, archive_root, "demo", "../escape", force=False)

            self.assertFalse(archive_root.exists())
            self.assertTrue(current.exists())

    def test_archive_rolls_back_when_recreate_current_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")

            with patch("spoon.commands.archive_cmd.create_current_layout", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    archive_current(repo, archive_root, "demo", "rollback", force=False)

            self.assertTrue(current.exists())
            self.assertTrue((current / "brief.md").exists())
            self.assertFalse(any((archive_root / "demo").glob("*-rollback")))

    def test_archive_reports_manual_recovery_when_partial_current_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")

            def fail_after_partial(repo_path):
                partial = repo_path / ".spoon" / "current"
                partial.mkdir(parents=True, exist_ok=True)
                (partial / "partial.txt").write_text("partial\n", encoding="utf-8")
                raise RuntimeError("partial recreate")

            with patch("spoon.commands.archive_cmd.create_current_layout", side_effect=fail_after_partial):
                with self.assertRaisesRegex(RuntimeError, "partial current directory exists"):
                    archive_current(repo, archive_root, "demo", "partial", force=False)

            self.assertTrue(current.exists())
            self.assertTrue((current / "partial.txt").exists())
            self.assertTrue(any((archive_root / "demo").glob("*-partial")))

    def test_archive_reports_manual_recovery_when_rollback_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            archive_root = Path(tmp) / "archives"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            current = repo / ".spoon" / "current"
            (current / "brief.md").write_text("# Brief\n\nbody\n", encoding="utf-8")
            (current / "plan.md").write_text("# Plan\n\nbody\n", encoding="utf-8")
            real_move = archive_cmd.shutil.move
            move_count = 0

            def fail_second_move(source, destination):
                nonlocal move_count
                move_count += 1
                if move_count == 2:
                    raise OSError("rollback locked")
                return real_move(source, destination)

            with patch("spoon.commands.archive_cmd.create_current_layout", side_effect=RuntimeError("boom")):
                with patch("spoon.commands.archive_cmd.shutil.move", side_effect=fail_second_move):
                    with self.assertRaisesRegex(RuntimeError, "rollback failed"):
                        archive_current(repo, archive_root, "demo", "rollback-fail", force=False)

            self.assertFalse(current.exists())
            self.assertTrue(any((archive_root / "demo").glob("*-rollback-fail")))


if __name__ == "__main__":
    unittest.main()
