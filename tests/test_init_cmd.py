import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout, run


class InitCommandTests(unittest.TestCase):
    def test_run_raises_for_non_git_repo_without_creating_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                run(Namespace(repo=repo))

            self.assertFalse((repo / ".spoon").exists())
            self.assertFalse((repo / ".git" / "info" / "exclude").exists())

    def test_create_current_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            current = repo / ".spoon" / "current"
            self.assertTrue((current / "brief.md").exists())
            self.assertTrue((current / "plan.md").exists())
            self.assertTrue((current / "review-board.md").exists())
            self.assertTrue((current / "handoff.md").exists())
            self.assertTrue((current / "metadata.json").exists())
            self.assertTrue((current / "prompts" / "final-plan-review.md").exists())
            self.assertTrue((current / "reviews" / "codex-plan.md").exists())
            self.assertTrue((current / "snapshots" / "status.txt").exists())

            exclude = repo / ".git" / "info" / "exclude"
            self.assertIn(".spoon/", exclude.read_text(encoding="utf-8"))

    def test_create_current_layout_supports_git_worktree_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            worktree = Path(tmp) / "worktree"
            main.mkdir()
            subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=main,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
                cwd=main,
                check=True,
                capture_output=True,
            )
            self.assertTrue((worktree / ".git").is_file())

            create_current_layout(worktree)

            self.assertTrue((worktree / ".spoon" / "current" / "brief.md").exists())
            result = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=worktree,
                check=True,
                text=True,
                capture_output=True,
            )
            exclude = Path(result.stdout.strip())
            if not exclude.is_absolute():
                exclude = worktree / exclude
            self.assertIn(".spoon/", exclude.read_text(encoding="utf-8"))

    def test_existing_brief_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            current = repo / ".spoon" / "current"
            current.mkdir(parents=True)
            (current / "brief.md").write_text("custom\n", encoding="utf-8")
            create_current_layout(repo)
            self.assertEqual((current / "brief.md").read_text(encoding="utf-8"), "custom\n")


if __name__ == "__main__":
    unittest.main()
