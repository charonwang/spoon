import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spoon.adapters.base import AdapterRequest, AdapterStatus
from spoon.adapters.claude_cli import (
    FORBIDDEN_FLAGS,
    ClaudeCapabilities,
    ClaudeCliAdapter,
    _humanize_stream_json_line,
    _parse_json_text,
    _parse_stream_json_lines,
    _validate_review_payload,
    render_claude_review,
)
from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import read_text, write_text
from spoon.paths import project_paths
from spoon.review_parser import classify_review_text
from spoon.spoon_config import TerminalConfig

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
        subprocess.run(["git", "init"], cwd=self.repo,
                       check=True, capture_output=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        # The prompt must go through stdin, not as a trailing positional after
        # --add-dir, which some claude builds treat as a variadic flag and would
        # otherwise swallow the prompt.
        self.assertEqual(kwargs.get("input"), read_text(self.prompt))
        add_dir_index = cmd.index("--add-dir")
        self.assertEqual(cmd[add_dir_index + 1], str(self.repo.resolve()))
        self.assertEqual(len(cmd), add_dir_index + 2)

    def test_build_cmd_includes_conversation_title(self):
        adapter = ClaudeCliAdapter(
            command="claude", conversation_title="Spoon:ST冒烟")
        capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
        cmd = adapter._build_cmd(
            self.repo, capabilities, use_schema=False, stream=False)
        self.assertIn("--name", cmd)
        self.assertIn("Spoon:ST冒烟", cmd)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_timeout_is_unavailable(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"], timeout=30)
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_execute_file_not_found_is_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude")
        adapter = ClaudeCliAdapter(command="missing-claude")
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli._detect_claude_capabilities", return_value=None)
    def test_missing_command_on_help_is_unavailable(self, _caps):
        result = ClaudeCliAdapter(
            command="missing-claude").execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_missing_json_output_flag_is_unavailable(self, mock_run):
        adapter = ClaudeCliAdapter()
        adapter._capabilities = ClaudeCapabilities(
            json_output=False, json_schema=False)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=True)
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
        adapter._capabilities = ClaudeCapabilities(
            json_output=True, json_schema=False)
        adapter.execute(self.request)
        cmd = mock_run.call_args.args[0]
        self.assertIn("--output-format", cmd)
        self.assertNotIn("--json-schema", cmd)
        prompt_arg = mock_run.call_args.kwargs["input"]
        self.assertIn("verdict", prompt_arg.lower())

    def test_parse_stream_json_lines_uses_last_valid_payload(self):
        lines = [
            json.dumps({"type": "progress", "message": "working"}),
            claude_json_stdout(VALID_PAYLOAD),
        ]
        payload = _parse_stream_json_lines(lines)
        self.assertEqual(payload["verdict"], "approved")

    def test_humanize_stream_json_shows_thinking_not_raw_json(self):
        thinking = json.dumps(
            {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "考虑计划质量"},
            }
        )
        human = _humanize_stream_json_line(thinking)
        self.assertEqual(human, "考虑计划质量")
        wrapped = json.dumps(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "thinking_delta", "thinking": "片段"},
                },
            }
        )
        self.assertEqual(_humanize_stream_json_line(wrapped), "片段")
        self.assertIsNone(
            _humanize_stream_json_line(
                json.dumps({"type": "system", "subtype": "thinking_tokens"})
            )
        )

    @patch("spoon.adapters.claude_cli.subprocess.Popen")
    def test_visible_mode_tees_humanized_stream_not_raw_json(self, mock_popen):
        stream_lines = (
            json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "thinking_delta", "thinking": "先看 brief"},
                }
            )
            + "\n"
            + claude_json_stdout(VALID_PAYLOAD)
            + "\n"
        )
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(stream_lines)
        mock_proc.stderr = io.StringIO("")
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        adapter = ClaudeCliAdapter(
            visible=True,
            terminal=TerminalConfig(launcher="inline"),
        )
        adapter._capabilities = ClaudeCapabilities(
            json_output=True,
            json_schema=True,
            stream_json=True,
            partial_messages=True,
        )
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        shown = stderr_capture.getvalue()
        self.assertIn("先看 brief", shown)
        self.assertIn("Claude review starting", shown)
        self.assertNotIn('"thinking_delta"', shown)

    @patch("spoon.adapters.claude_cli.subprocess.Popen")
    def test_visible_mode_drains_claude_stderr_while_running(self, mock_popen):
        stream_line = claude_json_stdout(VALID_PAYLOAD) + "\n"
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(stream_line)
        mock_proc.stderr = io.StringIO("verbose: working\n")
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        adapter = ClaudeCliAdapter(
            visible=True,
            terminal=TerminalConfig(launcher="inline"),
        )
        adapter._capabilities = ClaudeCapabilities(
            json_output=True,
            json_schema=True,
            stream_json=True,
            partial_messages=True,
        )
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        combined = stderr_capture.getvalue()
        self.assertIn("verbose: working", combined)
        self.assertIn("Claude review", combined)

    @patch("spoon.adapters.claude_cli.wait_for_exit_file", return_value=0)
    @patch("spoon.adapters.claude_cli.launch_external_terminal")
    @patch("spoon.adapters.claude_cli.resolve_terminal")
    def test_visible_windows_terminal_uses_external_launch(
        self,
        mock_resolve,
        mock_launch,
        mock_wait,
    ):
        from spoon.adapters.terminal_launch import ResolvedTerminal

        capture_holder: dict[str, Path] = {}

        def _resolve(config, *, cwd, job_path):
            job = __import__("json").loads(
                job_path.read_text(encoding="utf-8"))
            capture_holder["path"] = Path(job["capture_path"])
            write_text(
                capture_holder["path"],
                claude_json_stdout(VALID_PAYLOAD) + "\n",
            )
            return ResolvedTerminal(
                launcher="windows_terminal",
                argv=["wt", "--", "python"],
                executable="wt",
                note="windows_terminal (wt)",
            )

        mock_resolve.side_effect = _resolve
        adapter = ClaudeCliAdapter(
            visible=True,
            ui="print",
            terminal=TerminalConfig(launcher="windows_terminal"),
        )
        adapter._capabilities = ClaudeCapabilities(
            json_output=True,
            json_schema=True,
            stream_json=True,
            partial_messages=True,
        )
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        mock_launch.assert_called_once()
        mock_wait.assert_called_once()
        self.assertTrue(self.output.is_file())

    @patch("spoon.adapters.claude_cli.subprocess.run")
    def test_visible_false_uses_headless_json(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=claude_json_stdout(VALID_PAYLOAD),
            stderr="",
        )
        adapter = ClaudeCliAdapter(visible=False)
        adapter._capabilities = ClaudeCapabilities(
            json_output=True,
            json_schema=True,
            stream_json=True,
            partial_messages=True,
        )
        adapter.execute(self.request)
        cmd = mock_run.call_args.args[0]
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)
        self.assertNotIn("stream-json", cmd)

    @patch("spoon.adapters.claude_cli.wait_for_nonempty_file")
    @patch("spoon.adapters.claude_cli.launch_external_terminal")
    @patch("spoon.adapters.claude_cli.resolve_terminal")
    def test_interactive_reuses_session_on_second_turn(
        self,
        mock_resolve,
        mock_launch,
        mock_wait,
    ):
        from spoon.adapters.terminal_launch import ResolvedTerminal

        review = (
            "# Claude Review\n\n## Verdict\n\napproved\n\n## Summary\n\nok\n\n"
            "## Findings\n\n## Blocking\n\nNo blockers, ready for implementation.\n\n"
            "## Should Fix\n\n- _None._\n\n## Optional\n\n- _None._\n\n"
            "## Test Gaps\n\n- _None._\n\n## Questions\n\n- _None._\n"
        )

        def _wait(path, *, timeout_seconds, stable_seconds=1.0):
            del timeout_seconds, stable_seconds
            write_text(path, review)
            return review

        mock_wait.side_effect = _wait
        mock_resolve.return_value = ResolvedTerminal(
            launcher="windows_terminal",
            argv=["wt", "--", "claude"],
            executable="wt",
            note="windows_terminal (wt)",
        )
        adapter = ClaudeCliAdapter(
            visible=True,
            ui="interactive",
            session_key="run-test",
            terminal=TerminalConfig(launcher="windows_terminal"),
        )
        adapter._capabilities = ClaudeCapabilities(
            json_output=True,
            json_schema=True,
            stream_json=True,
            partial_messages=True,
        )

        first = adapter.execute(self.request)
        self.assertEqual(first.status, AdapterStatus.SUCCESS)
        first_cmd = mock_resolve.call_args.kwargs["inner_argv"]
        self.assertIn("--session-id", first_cmd)
        self.assertNotIn("--resume", first_cmd)

        write_text(self.output, "")
        second = adapter.execute(self.request)
        self.assertEqual(second.status, AdapterStatus.SUCCESS)
        second_cmd = mock_resolve.call_args.kwargs["inner_argv"]
        self.assertIn("--resume", second_cmd)
        self.assertNotIn("--session-id", second_cmd)
        sid = first_cmd[first_cmd.index("--session-id") + 1]
        self.assertEqual(second_cmd[second_cmd.index("--resume") + 1], sid)


if __name__ == "__main__":
    unittest.main()
