import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.adapters.base import AdapterRequest, AdapterStatus
from spoon.adapters.claude_cli import (
    FORBIDDEN_FLAGS,
    ClaudeCapabilities,
    ClaudeCliAdapter,
    _parse_json_text,
    _validate_review_payload,
    render_claude_review,
)
from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import read_text, write_text
from spoon.paths import project_paths
from spoon.review_parser import classify_review_text

VALID_PAYLOAD = {
    "verdict": "approved",
    "summary": "Plan looks good.",
    "findings_markdown": "",
}

FINDINGS_PAYLOAD = {
    "verdict": "changes_requested",
    "summary": "Needs follow-up.",
    "findings_markdown": "### Should Fix\n\n- Add route coverage.\n",
}


def claude_json_stdout(payload: dict[str, str]) -> str:
    return json.dumps({"result": json.dumps(payload)})


class ClaudeCliAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        self.prompt = self.paths.current / "prompts" / "claude-plan-review.md"
        self.output = self.paths.current / "reviews" / "claude-plan.md"
        write_text(self.prompt, "Review the plan.\n")
        self.request = AdapterRequest(
            action_id="abc123",
            prompt_path=".spoon/current/prompts/claude-plan-review.md",
            output_path=".spoon/current/reviews/claude-plan.md",
            working_directory=str(self.repo),
            timeout_seconds=30,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_render_includes_all_required_headings(self):
        rendered = render_claude_review(VALID_PAYLOAD)
        self.assertIn("## Verdict", rendered)
        self.assertIn("## Summary", rendered)
        self.assertIn("## Findings", rendered)

    def test_render_passes_classify_review_text_for_empty_findings(self):
        rendered = render_claude_review(VALID_PAYLOAD)
        groups = classify_review_text("claude-plan.md", rendered)
        warnings = groups["Needs Triage"]
        self.assertFalse(any("[PARSER WARNING]" in item for item in warnings))

    def test_render_passes_classify_review_text_for_structured_findings(self):
        rendered = render_claude_review(FINDINGS_PAYLOAD)
        groups = classify_review_text("claude-plan.md", rendered)
        warnings = groups["Needs Triage"]
        self.assertFalse(any("[PARSER WARNING]" in item for item in warnings))
        self.assertTrue(groups["Should Fix"])

    def test_validate_review_payload_rejects_non_string_summary(self):
        with self.assertRaisesRegex(ValueError, "summary must be a string"):
            _validate_review_payload(
                {"verdict": "approved", "summary": 123, "findings_markdown": ""}
            )

    def test_validate_review_payload_rejects_extra_fields(self):
        with self.assertRaisesRegex(ValueError, "unexpected review fields"):
            _validate_review_payload(
                {
                    "verdict": "approved",
                    "summary": "ok",
                    "findings_markdown": "",
                    "extra": 1,
                }
            )

    def test_parse_json_text_falls_back_when_result_is_not_json(self):
        payload = _parse_json_text(
            json.dumps({"result": "not-json", **VALID_PAYLOAD})
        )
        self.assertEqual(payload["verdict"], "approved")

    def test_parse_json_text_rejects_direct_extra_fields(self):
        with self.assertRaisesRegex(ValueError, "unexpected review fields"):
            _parse_json_text(
                json.dumps(
                    {
                        "verdict": "approved",
                        "summary": "ok",
                        "findings_markdown": "",
                        "extra": 1,
                    }
                )
            )

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_success_writes_all_headings(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(VALID_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter(command="claude")
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        text = read_text(self.output)
        self.assertIn("## Verdict", text)
        self.assertIn("## Summary", text)
        self.assertIn("## Findings", text)
        self.assertNotIn("Verdict: approved", text)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_success_writes_structured_findings(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(FINDINGS_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter(command="claude")
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        text = read_text(self.output)
        self.assertIn("Add route coverage.", text)
        groups = classify_review_text("claude-plan.md", text)
        self.assertFalse(
            any("[PARSER WARNING]" in item for item in groups["Needs Triage"])
        )

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_uses_argument_list_without_shell(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(VALID_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter(command="claude", model="sonnet")
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        adapter.execute(self.request)
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertFalse(kwargs.get("shell", False))
        cmd = mock_run.call_args.args[0]
        self.assertIsInstance(cmd, list)
        for flag in FORBIDDEN_FLAGS:
            self.assertNotIn(flag, cmd)
        self.assertIn("--json-schema", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("--add-dir", cmd)
        self.assertIn("sonnet", cmd)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_timeout_is_unavailable(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=30)
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)
        self.assertIn("timed out", result.message.lower())

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_auth_failure_reads_stdout_and_stderr(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout="Authentication required. Please login.",
            stderr="warning: deprecated flag",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_file_not_found_is_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude")
        adapter = ClaudeCliAdapter(command="missing-claude")
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli._detect_claude_capabilities", return_value=None)
    def test_missing_command_on_help_is_unavailable(self, _caps):
        result = ClaudeCliAdapter(command="missing-claude").execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_missing_json_output_flag_is_unavailable(self, mock_run):
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=False, json_schema=False)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)
        mock_run.assert_not_called()

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_empty_stdout_fails(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="",
            stderr="",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.FAILED)
        self.assertIn("empty claude output", result.message)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_bad_json_fails_without_overwriting_existing_review(self, mock_run):
        write_text(self.output, render_claude_review(VALID_PAYLOAD))
        original = read_text(self.output)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="not-json",
            stderr="",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.FAILED)
        self.assertEqual(read_text(self.output), original)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_refuses_to_overwrite_existing_valid_review(self, mock_run):
        write_text(self.output, render_claude_review(VALID_PAYLOAD))
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(FINDINGS_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.FAILED)
        self.assertIn("overwrite", result.message.lower())

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_rejects_parser_warning_payload(self, mock_run):
        bad_payload = {
            "verdict": "approved",
            "summary": "ok",
            "findings_markdown": "Unstructured prose without headings.",
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(bad_payload),
            stderr="",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.FAILED)
        self.assertIn("parser warnings", result.message.lower())

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_without_json_schema_uses_prompt_constraint(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps(VALID_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(json_output=True, json_schema=False)
        adapter.execute(self.request)
        cmd = mock_run.call_args.args[0]
        self.assertIn("--output-format", cmd)
        self.assertNotIn("--json-schema", cmd)
        prompt_arg = cmd[-1]
        self.assertIn("verdict", prompt_arg.lower())


if __name__ == "__main__":
    unittest.main()
