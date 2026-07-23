import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spoon.adapters.base import AdapterRequest, AdapterStatus
from spoon.adapters.codex_cli import CodexCliAdapter
from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import read_text, write_text
from spoon.paths import project_paths

_REVIEW_OK = (
    "## Verdict\n\napproved\n\n## Summary\n\nLooks good.\n\n"
    "## Findings\n\n### Optional\n\n- _None._\n"
)


class CodexCliAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo,
                       check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        self.prompt = self.paths.current / "prompts" / "codex-plan-review.md"
        self.output = self.paths.current / "reviews" / "codex-plan.md"
        write_text(self.prompt, "Review the plan.\n")
        self.request = AdapterRequest(
            action_id="abc123",
            prompt_path=".spoon/current/prompts/codex-plan-review.md",
            output_path=".spoon/current/reviews/codex-plan.md",
            working_directory=str(self.repo),
            timeout_seconds=30,
            phase="plan_review",
        )

    def tearDown(self):
        self.tmp.cleanup()

    @patch("spoon.adapters.codex_cli.subprocess.run")
    def test_execute_runs_codex_exec_read_only(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex", "exec"],
            returncode=0,
            stdout=_REVIEW_OK,
            stderr="",
        )

        result = CodexCliAdapter().execute(self.request)

        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        self.assertIn("Looks good.", read_text(self.output))
        cmd = mock_run.call_args.args[0]
        self.assertTrue(Path(cmd[0]).name.lower().startswith("codex"))
        self.assertEqual(cmd[1], "exec")
        self.assertIn("-C", cmd)
        self.assertIn(str(self.repo.resolve()), cmd)
        self.assertIn("-s", cmd)
        self.assertIn("read-only", cmd)
        self.assertEqual(
            mock_run.call_args.kwargs["input"], "Review the plan.\n")

    def test_build_cmd_includes_model_effort_and_service_tier(self):
        adapter = CodexCliAdapter(
            model="gpt-5.6-sol",
            reasoning_effort="high",
            service_tier="fast",
        )
        cmd = adapter._build_cmd(self.repo)
        self.assertIn("-m", cmd)
        self.assertIn("gpt-5.6-sol", cmd)
        self.assertIn("-c", cmd)
        self.assertIn("model_reasoning_effort=high", cmd)
        self.assertIn("service_tier=fast", cmd)

    @patch("spoon.adapters.codex_cli.subprocess.run")
    def test_execute_rejects_parser_warnings(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex", "exec"],
            returncode=0,
            stdout="## Findings\n\nplain paragraph\n",
            stderr="",
        )

        result = CodexCliAdapter().execute(self.request)

        self.assertEqual(result.status, AdapterStatus.FAILED)
        self.assertFalse(read_text(self.output).strip())

    @patch("spoon.adapters.codex_cli.subprocess.run")
    def test_execute_reports_auth_failure_as_unavailable(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["codex", "exec"],
            returncode=1,
            stdout="",
            stderr="login required",
        )

        result = CodexCliAdapter().execute(self.request)

        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)
        self.assertIn("authentication", result.message)

    @patch("spoon.adapters.codex_cli.sys.stderr", new_callable=io.StringIO)
    @patch("spoon.adapters.codex_cli.subprocess.Popen")
    def test_visible_execute_drains_stdout_and_stderr(self, mock_popen, stderr):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = io.StringIO(_REVIEW_OK)
        proc.stderr = io.StringIO("progress\n")
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        result = CodexCliAdapter(visible=True).execute(self.request)

        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        self.assertIn("Looks good.", read_text(self.output))
        self.assertIn("progress", stderr.getvalue())
        proc.stdin.write.assert_called_once_with("Review the plan.\n")
        proc.stdin.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
