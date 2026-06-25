import errno
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands.export_cmd import run as export_run
from spoon.commands.init_cmd import create_current_layout
from spoon.commands.snapshot_cmd import create_snapshot
from spoon.export_policy import (
    ALLOWED_EXPORT_FILENAMES,
    BUSINESS_REVIEW_WARNING,
    PLAN_REVIEW_WARNING,
    ExportSeverity,
    build_github_export,
    discover_task_export_dirs,
    export_task_dir,
    render_export_report,
    scan_export_tree,
    scan_text_content,
    validate_slug,
    validate_snapshot_summary,
)
from spoon.io_util import read_text, write_text
from spoon.paths import project_paths


class GitHubExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        write_text(self.paths.brief, "# Brief\n\nExport test.\n")
        write_text(self.paths.plan, "# Plan\n\nDo the thing.\n")
        create_snapshot(self.repo, test_cmd=None, dependency_cmd=None)

    def tearDown(self):
        self.tmp.cleanup()

    def _destination(self, name: str = "export-root") -> Path:
        return Path(self.tmp.name) / name

    def test_successful_export_contains_allowlist_only(self):
        destination = self._destination()
        result = build_github_export(self.repo, destination, "demo", "task-1")
        self.assertTrue(result.ok)
        task_dir = export_task_dir(destination, "demo", "task-1")
        self.assertTrue(task_dir.is_dir())
        names = {path.name for path in task_dir.iterdir() if path.is_file()}
        self.assertTrue(names.issubset(ALLOWED_EXPORT_FILENAMES))
        self.assertIn("brief.md", names)
        self.assertIn("plan.md", names)
        self.assertIn("snapshot-summary.json", names)
        self.assertIn("export-report.md", names)
        self.assertFalse(any((self.paths.snapshots / name).exists() for name in names))

    def test_snapshot_summary_raw_snapshots_false(self):
        destination = self._destination("export-root-2")
        build_github_export(self.repo, destination, "demo", "task-2")
        summary_path = export_task_dir(destination, "demo", "task-2") / "snapshot-summary.json"
        summary = json.loads(read_text(summary_path))
        self.assertFalse(summary["raw_snapshots_exported"])
        self.assertIn(summary["test_status"], {"passed", "failed", "not_run", "unknown"})

    def test_destination_must_not_exist(self):
        destination = self._destination("export-root-3")
        destination.mkdir()
        result = build_github_export(self.repo, destination, "demo", "task-3")
        self.assertFalse(result.ok)
        self.assertFalse(export_task_dir(destination, "demo", "task-3").exists())

    def test_invalid_slug_is_blocking(self):
        destination = self._destination("export-root-4")
        self.assertIsNotNone(validate_slug("../bad", "project"))
        result = build_github_export(self.repo, destination, "../bad", "task-4")
        self.assertFalse(result.ok)

    def test_uppercase_slug_reports_lowercase_requirement(self):
        finding = validate_slug("Demo", "project")
        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertIn("lowercase", finding.message)

    def test_empty_markdown_repo_exports_minimal_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "empty-repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            paths = project_paths(repo)
            write_text(paths.brief, "")
            write_text(paths.plan, "")
            write_text(paths.review_board, "")
            write_text(paths.handoff, "")
            destination = Path(tmp) / "export-empty"
            result = build_github_export(repo, destination, "demo", "empty-task")
            self.assertTrue(result.ok)
            task_dir = export_task_dir(destination, "demo", "empty-task")
            names = {path.name for path in task_dir.iterdir() if path.is_file()}
            self.assertIn("snapshot-summary.json", names)
            self.assertIn("index.json", names)
            self.assertIn("export-report.md", names)
            self.assertNotIn("brief.md", names)

    def test_all_four_markdown_files_export_when_filled(self):
        destination = self._destination("export-root-all-md")
        write_text(self.paths.review_board, "# Board\n\nFindings here.\n")
        write_text(self.paths.handoff, "# Handoff\n\nApproved work.\n")
        result = build_github_export(self.repo, destination, "demo", "task-all-md")
        self.assertTrue(result.ok)
        task_dir = export_task_dir(destination, "demo", "task-all-md")
        names = {path.name for path in task_dir.iterdir() if path.is_file()}
        for name in ("brief.md", "plan.md", "review-board.md", "handoff.md"):
            self.assertIn(name, names)

    def test_export_report_content(self):
        destination = self._destination("export-root-report")
        result = build_github_export(self.repo, destination, "demo", "task-report")
        self.assertTrue(result.ok)
        report = read_text(export_task_dir(destination, "demo", "task-report") / "export-report.md")
        self.assertEqual(report, render_export_report(result.findings))
        self.assertIn("# Export Report", report)
        self.assertIn("Blocking findings: 0", report)
        self.assertIn("## Warnings", report)
        self.assertIn(f"`brief.md`: {BUSINESS_REVIEW_WARNING}", report)
        self.assertIn(f"`plan.md`: {PLAN_REVIEW_WARNING}", report)
        self.assertRegex(report, r"Generated at: .+(?:[+-]\d{2}:\d{2}|Z)")

    def test_snapshot_summary_rejects_non_integer_changed_file_count(self):
        findings = validate_snapshot_summary(
            {
                "captured_at": "2026-06-25T12:00:00+08:00",
                "changed_file_count": "3",
                "test_status": "not_run",
                "dependency_check": "not_run",
                "sensitive_scan": "unknown",
                "raw_snapshots_exported": False,
            },
            "snapshot-summary.json",
        )
        self.assertTrue(
            any("changed_file_count" in item.message for item in findings),
        )

    def test_scan_export_tree_rejects_nested_allowlisted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "extra"
            nested.mkdir()
            write_text(nested / "brief.md", "# Brief\n\nnested\n")
            findings = scan_export_tree(root)
            self.assertTrue(
                any(
                    item.severity is ExportSeverity.BLOCKING
                    and item.source == "extra/brief.md"
                    for item in findings
                ),
            )

    def test_discover_task_export_dirs_finds_tasks_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_root = Path(tmp) / "tasks"
            task_a = tasks_root / "demo" / "task-a"
            task_b = tasks_root / "demo" / "task-b"
            task_b.mkdir(parents=True)
            task_a.mkdir(parents=True)
            discovered = discover_task_export_dirs(tasks_root)
            self.assertEqual(
                [path.name for path in discovered],
                ["task-a", "task-b"],
            )

    def test_discover_task_export_dirs_empty_tasks_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_root = Path(tmp) / "tasks"
            tasks_root.mkdir()
            self.assertEqual(discover_task_export_dirs(tasks_root), [])

    def test_validate_exports_discovers_multiple_tasks(self):
        destination = self._destination("export-root-multi")
        build_github_export(self.repo, destination, "demo", "task-one")
        tasks_root = destination / "tasks"
        task_two = tasks_root / "demo" / "task-two"
        task_two.mkdir(parents=True)
        write_text(task_two / "brief.md", "# Brief\n\nsecond task\n")
        write_text(task_two / "index.json", '{"schema_version":1}\n')
        write_text(
            task_two / "snapshot-summary.json",
            json.dumps(
                {
                    "captured_at": "2026-06-25T12:00:00+08:00",
                    "changed_file_count": 0,
                    "test_status": "not_run",
                    "dependency_check": "not_run",
                    "sensitive_scan": "unknown",
                    "raw_snapshots_exported": False,
                }
            )
            + "\n",
        )
        write_text(task_two / "export-report.md", "# Export Report\n\nNo findings.\n")
        script = (
            Path(__file__).resolve().parents[1]
            / "github"
            / "history-template"
            / "scripts"
            / "validate_exports.py"
        )
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(tasks_root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("validating", proc.stdout)
        self.assertIn("task-one", proc.stdout)
        self.assertIn("task-two", proc.stdout)
        self.assertIn("blocking=0", proc.stdout)

    def test_scan_export_tree_allows_snapshots_in_segment_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-project-snapshots"
            root.mkdir()
            write_text(root / "brief.md", "# Brief\n\nok\n")
            write_text(root / "index.json", '{"schema_version":1}\n')
            write_text(root / "snapshot-summary.json", json.dumps({
                "captured_at": "2026-06-25T12:00:00+08:00",
                "changed_file_count": 0,
                "test_status": "not_run",
                "dependency_check": "not_run",
                "sensitive_scan": "unknown",
                "raw_snapshots_exported": False,
            }) + "\n")
            write_text(root / "export-report.md", "# Export Report\n\nNo findings.\n")
            findings = scan_export_tree(root)
            self.assertFalse(
                any("raw snapshot paths" in item.message for item in findings),
            )

    def test_destination_mkdir_race_returns_blocking(self):
        destination = self._destination("export-root-race")
        real_mkdir = Path.mkdir

        def mkdir_side_effect(self, mode=0o777, parents=False, exist_ok=False):
            if self.resolve() == destination.resolve() and not exist_ok:
                raise FileExistsError(errno.EEXIST, "File exists", str(self))
            return real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

        with patch.object(Path, "mkdir", mkdir_side_effect):
            result = build_github_export(self.repo, destination, "demo", "task-race")
        self.assertFalse(result.ok)
        self.assertFalse(export_task_dir(destination, "demo", "task-race").exists())
        self.assertTrue(
            any(
                item.severity is ExportSeverity.BLOCKING
                and "destination already exists" in item.message
                for item in result.findings
            ),
        )

    def test_unresolved_local_path_blocks_scan(self):
        findings = scan_text_content(r"D:\secret\outside\file.go:82", "plan.md")
        self.assertTrue(
            any("local path token" in item.message for item in findings),
        )

    def test_outside_repo_path_in_markdown_is_rewritten(self):
        destination = self._destination("export-root-5b")
        write_text(self.paths.plan, "See D:\\outside\\repo\\file.go:82\n")
        result = build_github_export(self.repo, destination, "demo", "task-5b")
        self.assertTrue(result.ok)
        plan = read_text(export_task_dir(destination, "demo", "task-5b") / "plan.md")
        self.assertIn("<local-path>", plan)
        self.assertTrue(
            any("rewrote" in item.message and "local path" in item.message for item in result.findings),
        )

    def test_session_id_blocks_export(self):
        destination = self._destination("export-root-6")
        write_text(self.paths.brief, "session_id: abc\n")
        result = build_github_export(self.repo, destination, "demo", "task-6")
        self.assertFalse(result.ok)

    def test_long_fence_blocks_export(self):
        destination = self._destination("export-root-7")
        fence_body = "\n".join(f"line {index}" for index in range(61))
        write_text(self.paths.plan, f"```go\n{fence_body}\n```\n")
        result = build_github_export(self.repo, destination, "demo", "task-7")
        self.assertFalse(result.ok)

    def test_brief_and_plan_emit_warnings(self):
        destination = self._destination("export-root-8")
        result = build_github_export(self.repo, destination, "demo", "task-8")
        self.assertTrue(result.ok)
        warnings = [item for item in result.findings if item.severity == ExportSeverity.WARNING]
        sources = {item.source for item in warnings}
        self.assertIn("brief.md", sources)
        self.assertIn("plan.md", sources)
        report = read_text(export_task_dir(destination, "demo", "task-8") / "export-report.md")
        self.assertIn("Warnings", report)

    def test_scan_export_tree_rejects_blocked_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "diff.patch", "secret diff")
            findings = scan_export_tree(root)
            self.assertTrue(any(item.severity == ExportSeverity.BLOCKING for item in findings))

    def test_scan_export_tree_rejects_disallowed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "notes.txt", "extra")
            findings = scan_export_tree(root)
            self.assertTrue(
                any("allowlist" in item.message for item in findings),
            )

    def test_export_cmd_success(self):
        destination = self._destination("export-root-9")
        code = export_run(
            type(
                "Args",
                (),
                {
                    "repo": self.repo,
                    "destination": destination,
                    "project": "demo",
                    "task": "task-9",
                },
            )()
        )
        self.assertEqual(code, 0)
        self.assertTrue(export_task_dir(destination, "demo", "task-9").is_dir())

    def test_history_template_validator_runs_on_valid_export(self):
        destination = self._destination("export-root-validator")
        build_github_export(self.repo, destination, "demo", "task-validator")
        task_dir = export_task_dir(destination, "demo", "task-validator")
        script = (
            Path(__file__).resolve().parents[1]
            / "github"
            / "history-template"
            / "scripts"
            / "validate_exports.py"
        )
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(task_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("blocking=0", proc.stdout)

    def test_export_cmd_returns_one_on_blocking(self):
        destination = self._destination("export-root-10")
        write_text(self.paths.brief, "thread_id: xyz\n")
        code = export_run(
            type(
                "Args",
                (),
                {
                    "repo": self.repo,
                    "destination": destination,
                    "project": "demo",
                    "task": "task-10",
                },
            )()
        )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
