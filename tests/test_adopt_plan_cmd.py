import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands import adopt_plan_cmd
from spoon.commands.adopt_plan_cmd import adopt_plan, find_bad_plan_links
from spoon.commands.init_cmd import create_current_layout


class AdoptPlanTests(unittest.TestCase):
    def test_adopt_plan_moves_source_and_writes_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")

            adopt_plan(repo, source, replace=False)

            plan = repo / ".spoon" / "current" / "plan.md"
            self.assertFalse(source.exists())
            text = plan.read_text(encoding="utf-8")
            self.assertIn("spoon adopted-plan", text)
            self.assertIn("# Cursor Plan", text)
            self.assertIn("Canonical source: .spoon/current/plan.md", text)

    def test_adopt_plan_leaves_source_intact_if_target_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            existing_plan = repo / ".spoon" / "current" / "plan.md"
            existing_plan.write_text("existing canonical plan\n", encoding="utf-8")
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")
            original_source = source.read_text(encoding="utf-8")
            original_plan = existing_plan.read_text(encoding="utf-8")

            with patch.object(
                adopt_plan_cmd,
                "_replace_file",
                side_effect=OSError("disk full"),
                create=True,
            ):
                with self.assertRaises(OSError):
                    adopt_plan(repo, source, replace=True)

            self.assertTrue(source.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), original_source)
            self.assertEqual(existing_plan.read_text(encoding="utf-8"), original_plan)
            temp_files = list((repo / ".spoon" / "current" / "plan.md").parent.glob(".adopt-plan-*.tmp"))
            self.assertEqual(temp_files, [])

    def test_adopt_plan_rolls_back_if_source_unlink_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")
            original_unlink = Path.unlink

            def fail_source_unlink(path, *args, **kwargs):
                if path == source:
                    raise OSError("locked")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_source_unlink):
                with self.assertRaisesRegex(OSError, "locked"):
                    adopt_plan(repo, source, replace=False)

            plan = repo / ".spoon" / "current" / "plan.md"
            plan_sources = repo / ".spoon" / "current" / "snapshots" / "plan-sources.txt"
            self.assertTrue(source.exists())
            self.assertFalse(plan.exists())
            self.assertFalse(plan_sources.exists())

    def test_adopt_plan_restores_existing_plan_if_source_unlink_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            plan = repo / ".spoon" / "current" / "plan.md"
            plan.write_text("existing plan\n", encoding="utf-8")
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")
            original_unlink = Path.unlink

            def fail_source_unlink(path, *args, **kwargs):
                if path == source:
                    raise OSError("locked")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_source_unlink):
                with self.assertRaisesRegex(OSError, "locked"):
                    adopt_plan(repo, source, replace=True)

            self.assertTrue(source.exists())
            self.assertEqual(plan.read_text(encoding="utf-8"), "existing plan\n")

    def test_adopt_plan_rolls_back_if_plan_sources_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")
            original_write_text = adopt_plan_cmd.write_text

            def fail_plan_sources(path, text):
                if path.name == "plan-sources.txt":
                    raise OSError("metadata failed")
                return original_write_text(path, text)

            with patch.object(adopt_plan_cmd, "write_text", side_effect=fail_plan_sources):
                with self.assertRaisesRegex(OSError, "metadata failed"):
                    adopt_plan(repo, source, replace=False)

            plan = repo / ".spoon" / "current" / "plan.md"
            plan_sources = repo / ".spoon" / "current" / "snapshots" / "plan-sources.txt"
            self.assertTrue(source.exists())
            self.assertFalse(plan.exists())
            self.assertFalse(plan_sources.exists())

    def test_adopt_plan_writes_git_exclude_when_init_was_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")

            adopt_plan(repo, source, replace=False)

            exclude = repo / ".git" / "info" / "exclude"
            self.assertIn(".spoon/", exclude.read_text(encoding="utf-8"))

    def test_adopt_plan_creates_missing_current_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("# Cursor Plan\n\nBody\n", encoding="utf-8")

            adopt_plan(repo, source, replace=False)

            plan = repo / ".spoon" / "current" / "plan.md"
            plan_sources = repo / ".spoon" / "current" / "snapshots" / "plan-sources.txt"
            self.assertTrue(plan.exists())
            self.assertTrue(plan_sources.exists())
            self.assertFalse(source.exists())

    def test_adopt_plan_refuses_existing_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            plan = repo / ".spoon" / "current" / "plan.md"
            plan.write_text("existing\n", encoding="utf-8")
            source = Path(tmp) / "cursor.plan.md"
            source.write_text("new\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                adopt_plan(repo, source, replace=False)

    def test_adopt_plan_rejects_canonical_plan_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            current = repo / ".spoon" / "current"
            current.mkdir(parents=True)
            plan = repo / ".spoon" / "current" / "plan.md"
            plan.write_text("existing\n", encoding="utf-8")
            snapshots = current / "snapshots"
            self.assertFalse(snapshots.exists())

            with self.assertRaises(ValueError):
                adopt_plan(repo, plan, replace=True)

            self.assertEqual(plan.read_text(encoding="utf-8"), "existing\n")
            self.assertFalse(snapshots.exists())

    def test_bad_link_detection(self):
        text = "See C:\\path\\to\\x.go:82 and C:/path/to/y.go:12"
        warnings = find_bad_plan_links(text)
        self.assertEqual(len(warnings), 2)

    def test_good_file_uri_is_not_reported(self):
        text = "See file:///C:/path/to/your/repo/internal/x.go#L82"
        self.assertEqual(find_bad_plan_links(text), [])

    def test_windows_backslash_line_link_is_reported(self):
        text = r"See C:\path\to\x.go:82 and \Users\example\x.go:12"
        self.assertEqual(len(find_bad_plan_links(text)), 2)


if __name__ == "__main__":
    unittest.main()
