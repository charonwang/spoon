import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spoon.adapters.base import AdapterRequest, AdapterStatus
from spoon.adapters.codex_app import (
    PROXY_CONNECT_RETRIES,
    CodexAppServerAdapter,
    _conversation_thread_name,
    _find_thread_id_by_name,
    _JsonRpcClient,
    _load_codex_threads,
)
from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import read_text, write_text
from spoon.paths import project_paths
from spoon.runner.events import load_events

_REVIEW_OK = (
    "## Verdict\n\napproved\n\n## Summary\n\nLooks good.\n\n"
    "## Findings\n\n### Optional\n\n- _None._\n"
)


class CodexAppServerAdapterTests(unittest.TestCase):
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

    def test_load_codex_threads_missing_is_empty(self):
        self.assertEqual(_load_codex_threads(self.paths), {})

    def test_turn_model_overrides_include_effort_and_tier(self):
        adapter = CodexAppServerAdapter(
            model="gpt-5.6-sol",
            reasoning_effort="low",
            service_tier="fast",
        )
        self.assertEqual(
            adapter._thread_model_overrides(),
            {"model": "gpt-5.6-sol"},
        )
        self.assertEqual(
            adapter._turn_model_overrides(),
            {
                "model": "gpt-5.6-sol",
                "effort": "low",
                "serviceTier": "fast",
            },
        )

    def test_find_thread_id_by_name_reads_flat_thread_entries(self):
        title = "Spoon:ST冒烟"
        listed = {
            "data": [
                {"id": "thread-1", "name": "other", "cwd": str(self.repo)},
                {"id": "thread-2", "name": title, "cwd": str(self.repo)},
            ]
        }
        self.assertEqual(_find_thread_id_by_name(listed, title), "thread-2")

    def test_conversation_thread_name_is_exact_title(self):
        self.assertEqual(
            _conversation_thread_name("Spoon:ST冒烟"),
            "Spoon:ST冒烟",
        )
        self.assertEqual(_conversation_thread_name("  "), "Spoon:current")

    def test_json_rpc_client_times_out_on_blocked_read(self):
        read_fd, write_fd = os.pipe()
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = os.fdopen(read_fd, "r", encoding="utf-8", newline="\n")
        proc.poll.return_value = None
        client = _JsonRpcClient(proc, deadline=time.monotonic() + 0.2)
        try:
            with self.assertRaisesRegex(TimeoutError, "timed out"):
                client._read_line()
        finally:
            os.close(write_fd)
            client.close()

    @patch.object(CodexAppServerAdapter, "_nudge_desktop_refresh")
    @patch.object(CodexAppServerAdapter, "_resolve_thread_id", return_value="thread-1")
    @patch.object(CodexAppServerAdapter, "_handshake")
    @patch.object(CodexAppServerAdapter, "_open_app_server_client")
    @patch("spoon.adapters.codex_app.subprocess.Popen")
    def test_run_app_server_launches_codex_app_before_stdio(
        self,
        mock_popen,
        mock_open_client,
        _handshake,
        _resolve_thread,
        mock_nudge,
    ):
        mock_client = MagicMock()
        mock_client.collect_turn_text.return_value = _REVIEW_OK
        mock_open_client.return_value = mock_client

        adapter = CodexAppServerAdapter()
        adapter._run_app_server(
            self.paths,
            self.request,
            self.repo,
            "prompt",
            30,
        )

        mock_popen.assert_called_once()
        launch_cmd = mock_popen.call_args.args[0]
        self.assertTrue(Path(launch_cmd[0]).name.lower().startswith("codex"))
        self.assertEqual(launch_cmd[1], "app")
        self.assertEqual(str(launch_cmd[2]), str(self.repo.resolve()))
        mock_open_client.assert_called_once()
        mock_client.close.assert_called_once()
        mock_nudge.assert_called_once_with(self.repo, thread_id="thread-1")
        _deadline = mock_open_client.call_args.kwargs["deadline"]
        self.assertGreater(_deadline, time.monotonic())

    @patch("spoon.adapters.codex_app._open_codex_thread_url")
    @patch.object(CodexAppServerAdapter, "_launch_codex_app")
    @patch("spoon.adapters.codex_app.subprocess.run")
    def test_nudge_desktop_refresh_opens_deep_link_and_activates(
        self, mock_run, mock_launch, mock_open_url
    ):
        adapter = CodexAppServerAdapter(conversation_title="Spoon:demo")
        with patch("spoon.adapters.codex_app.sys.platform", "win32"):
            adapter._nudge_desktop_refresh(self.repo, thread_id="thread-xyz")
        mock_open_url.assert_called_once_with("codex://threads/thread-xyz")
        mock_launch.assert_called_once()
        mock_run.assert_called_once()
        self.assertIn("AppActivate", mock_run.call_args.args[0][3])

    @patch("spoon.adapters.codex_app.subprocess.Popen")
    def test_launch_codex_app_is_fire_and_forget(self, mock_popen):
        adapter = CodexAppServerAdapter()
        adapter._launch_codex_app(self.repo)
        mock_popen.assert_called_once()
        self.assertNotIn("timeout", mock_popen.call_args.kwargs)

    @patch("spoon.adapters.codex_app.subprocess.Popen")
    def test_launch_codex_app_missing_command_raises(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("missing")
        adapter = CodexAppServerAdapter()
        with self.assertRaisesRegex(RuntimeError, "codex command not found"):
            adapter._launch_codex_app(self.repo)

    @patch("spoon.adapters.codex_app.subprocess.Popen")
    def test_open_app_server_client_uses_stdio(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        adapter = CodexAppServerAdapter()
        client = adapter._open_app_server_client(
            self.repo, deadline=time.monotonic() + 5
        )
        try:
            cmd = mock_popen.call_args.args[0]
            self.assertTrue(Path(cmd[0]).name.lower().startswith("codex"))
            self.assertEqual(cmd[1:], ["app-server", "--stdio"])
        finally:
            client.close()

    @patch.object(CodexAppServerAdapter, "_launch_codex_app")
    def test_run_app_server_retries_share_overall_deadline(self, _launch):
        adapter = CodexAppServerAdapter()
        deadlines: list[float] = []

        def fake_open(cwd, *, deadline):
            deadlines.append(deadline)
            raise TimeoutError("codex app-server timed out")

        with patch.object(adapter, "_open_app_server_client", side_effect=fake_open):
            with self.assertRaises(RuntimeError):
                adapter._run_app_server(
                    self.paths,
                    self.request,
                    self.repo,
                    "prompt",
                    30,
                )

        self.assertEqual(len(deadlines), PROXY_CONNECT_RETRIES)
        self.assertEqual(len(set(deadlines)), 1)

    @patch("spoon.adapters.codex_app.CodexAppServerAdapter._run_app_server")
    def test_execute_app_server_success(self, mock_app_server):
        mock_app_server.return_value = _REVIEW_OK
        adapter = CodexAppServerAdapter()
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.SUCCESS)
        self.assertTrue(self.output.is_file())

    @patch("spoon.adapters.codex_app.CodexAppServerAdapter._run_app_server")
    def test_execute_surfaces_app_server_failure(self, mock_app_server):
        mock_app_server.side_effect = RuntimeError("proxy unavailable")
        adapter = CodexAppServerAdapter()
        result = adapter.execute(self.request)
        self.assertEqual(result.status, AdapterStatus.UNAVAILABLE)
        self.assertIn("app-server failed", result.message)
        self.assertIn("proxy unavailable", result.message)
        events = load_events(self.paths)
        self.assertTrue(
            any(item.get("type") == "codex_desktop_failed" for item in events))


if __name__ == "__main__":
    unittest.main()
