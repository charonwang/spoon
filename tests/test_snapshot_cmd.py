import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands import snapshot_cmd
from spoon.commands.init_cmd import create_current_layout
from spoon.commands.snapshot_cmd import create_snapshot, git_text
from spoon.git_util import current_head_or_empty
from spoon.paths import project_paths


def git_commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Spoon Test",
            "-c",
            "user.email=spoon@example.com",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class SnapshotCommandTests(unittest.TestCase):
    def test_snapshot_writes_git_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            (repo / "file.txt").write_text("hello\n", encoding="utf-8")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            snapshots = repo / ".spoon" / "current" / "snapshots"
            self.assertIn("file.txt", (snapshots / "status.txt").read_text(encoding="utf-8"))
            self.assertTrue((snapshots / "diff-stat.txt").exists())
            self.assertTrue((snapshots / "diff.patch").exists())
            self.assertTrue((snapshots / "recent-commits.txt").exists())

    def test_snapshot_includes_staged_only_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            (repo / "staged.txt").write_text("staged only\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True, capture_output=True)

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            snapshots = repo / ".spoon" / "current" / "snapshots"
            self.assertIn("staged.txt", (snapshots / "diff-stat.txt").read_text(encoding="utf-8"))
            self.assertIn("+staged only", (snapshots / "diff.patch").read_text(encoding="utf-8"))

    def test_snapshot_includes_untracked_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            (repo / "new_feature.py").write_text("print('new')\n", encoding="utf-8")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            snapshots = repo / ".spoon" / "current" / "snapshots"
            self.assertIn("new_feature.py", (snapshots / "diff-stat.txt").read_text(encoding="utf-8"))
            diff = (snapshots / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("## Untracked Files", diff)
            self.assertIn("+++ b/new_feature.py", diff)
            self.assertIn("+print('new')", diff)

    def test_snapshot_includes_committed_diff_since_implementation_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            paths = project_paths(repo)
            (repo / "app.txt").write_text("before\n", encoding="utf-8")
            git_commit(repo, "initial")
            paths.implementation_base.write_text(current_head_or_empty(repo) + "\n", encoding="utf-8")

            (repo / "app.txt").write_text("before\nafter checkpoint\n", encoding="utf-8")
            git_commit(repo, "checkpoint")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            snapshots = repo / ".spoon" / "current" / "snapshots"
            stat = (snapshots / "diff-stat.txt").read_text(encoding="utf-8")
            diff = (snapshots / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("Committed Since Implementation Base Diff Stat", stat)
            self.assertIn("app.txt", stat)
            self.assertIn("Committed Since Implementation Base", diff)
            self.assertIn("+after checkpoint", diff)

    def test_snapshot_falls_back_to_base_file_when_implementation_json_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            paths = project_paths(repo)
            (repo / "app.txt").write_text("before\n", encoding="utf-8")
            git_commit(repo, "initial")
            paths.implementation_base.write_text(current_head_or_empty(repo) + "\n", encoding="utf-8")
            paths.implementation.write_text("{bad", encoding="utf-8")

            (repo / "app.txt").write_text("before\nafter checkpoint\n", encoding="utf-8")
            git_commit(repo, "checkpoint")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            diff = (paths.snapshots / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("Implementation Base Warning", diff)
            self.assertIn("implementation.json was invalid and was skipped", diff)
            self.assertIn("+after checkpoint", diff)

    def test_snapshot_reports_ls_files_failure_in_untracked_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            real_run_git = snapshot_cmd.run_git

            def fail_ls_files(repo_arg, args):
                if args[:1] == ["ls-files"]:
                    return subprocess.CompletedProcess(
                        ["git", *args],
                        128,
                        "",
                        "fatal: bad index\n",
                    )
                return real_run_git(repo_arg, args)

            with patch.object(snapshot_cmd, "run_git", side_effect=fail_ls_files):
                create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            snapshots = repo / ".spoon" / "current" / "snapshots"
            stat = (snapshots / "diff-stat.txt").read_text(encoding="utf-8")
            diff = (snapshots / "diff.patch").read_text(encoding="utf-8")
            self.assertIn("git ls-files failed (exit 128)", stat)
            self.assertIn("fatal: bad index", stat)
            self.assertIn("git ls-files failed (exit 128)", diff)
            self.assertIn("fatal: bad index", diff)

    def test_snapshot_calls_ls_files_once_for_untracked_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            (repo / "new_feature.py").write_text("print('new')\n", encoding="utf-8")
            real_run_git = snapshot_cmd.run_git
            ls_files_calls = 0

            def count_ls_files(repo_arg, args):
                nonlocal ls_files_calls
                if args[:1] == ["ls-files"]:
                    ls_files_calls += 1
                return real_run_git(repo_arg, args)

            with patch.object(snapshot_cmd, "run_git", side_effect=count_ls_files):
                create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            self.assertEqual(ls_files_calls, 1)

    def test_snapshot_records_test_command_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            create_snapshot(repo, test_cmd="python --version", dependency_cmd=None)

            output = repo / ".spoon" / "current" / "snapshots" / "test-output.txt"
            self.assertIn("Command: python --version", output.read_text(encoding="utf-8"))

    def test_snapshot_updates_metadata_and_dependency_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            create_snapshot(repo, test_cmd=None, dependency_cmd="python --version")

            metadata = json.loads((repo / ".spoon" / "current" / "metadata.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(metadata["last_snapshot_at"])
            dependency_path = repo / ".spoon" / "current" / "snapshots" / "dependency-check.txt"
            dependency_output = dependency_path.read_text(encoding="utf-8")
            self.assertIn("Command: python --version", dependency_output)
            self.assertIn("Exit code:", dependency_output)

    def test_snapshot_recovers_corrupt_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            metadata_path = repo / ".spoon" / "current" / "metadata.json"
            metadata_path.write_text("{not json", encoding="utf-8")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(metadata["last_snapshot_at"])
            self.assertIn("metadata_warning", metadata)

    def test_snapshot_preserves_custom_sensitive_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            sensitive_scan = repo / ".spoon" / "current" / "snapshots" / "sensitive-scan.txt"
            sensitive_scan.write_text("# Sensitive Scan\n\nManual notes.\n", encoding="utf-8")

            create_snapshot(repo, test_cmd=None, dependency_cmd=None)

            self.assertEqual(
                sensitive_scan.read_text(encoding="utf-8"),
                "# Sensitive Scan\n\nManual notes.\n",
            )

    def test_git_text_reports_nonzero_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

            text = git_text(repo, ["not-a-real-git-command"])

            self.assertIn("Command failed: git not-a-real-git-command", text)
            self.assertIn("Exit code:", text)


if __name__ == "__main__":
    unittest.main()
