import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.adapters.base import AdapterRequest, AdapterResult, AdapterStatus
from spoon.commands.action_cmd import run_complete
from spoon.commands.adopt_plan_cmd import adopt_plan
from spoon.commands.init_cmd import create_current_layout
from spoon.constants import GENERATED_END, GENERATED_START
from spoon.io_util import write_text
from spoon.paths import project_paths
from spoon.runner.actions import load_actions
from spoon.runner.engine import advance
from spoon.runner.model import ActionKind, ActionStatus, RunPhase, RunStatus
from spoon.runner.state_store import load_implementation, load_run_state


class FakeClaudeAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        output = Path(request.working_directory) / request.output_path
        output.parent.mkdir(parents=True, exist_ok=True)
        write_text(
            output,
            "## Verdict\n\napproved\n\n## Summary\n\nok\n",
        )
        return AdapterResult(status=AdapterStatus.SUCCESS, message="ok")


class TimeoutAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        return AdapterResult(status=AdapterStatus.UNAVAILABLE, message="timeout")


def approved_board() -> str:
    return (
        "# Review Board\n\n"
        "## Decisions\n\n"
        "### Accepted For Handoff\n\n"
        "- Add route test.\n\n"
        "### Parked\n\n"
        "### Rejected\n\n"
        f"{GENERATED_START}\n"
        "## Generated Findings\n\n"
        "### Blocking\n\n_None._\n\n"
        "### Should Fix\n\n_None._\n\n"
        "### Optional\n\n_None._\n\n"
        "### Test Gaps\n\n_None._\n\n"
        "### Needs Triage\n\n_None._\n"
        f"{GENERATED_END}\n"
    )


class V2AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        self.adapters = {"claude_review": FakeClaudeAdapter()}

    def tearDown(self):
        self.tmp.cleanup()

    def _adopt_plan(self):
        source = self.repo / "cursor.plan.md"
        source.write_text("# Plan\n\nImplement route test.\n", encoding="utf-8")
        adopt_plan(self.repo, source, replace=False)

    def _complete_host_actions(self, result):
        for action in result.actions:
            if action.output_path:
                output = self.repo / action.output_path
                output.parent.mkdir(parents=True, exist_ok=True)
                write_text(
                    output,
                    "## Verdict\n\napproved\n\n## Summary\n\nhost ok\n",
                )
                run_complete(
                    type("Args", (), {
                        "repo": self.repo,
                        "action_id": action.id,
                        "output": output,
                    })()
                )

    def _drive_to_archive_ready(self):
        self._adopt_plan()
        write_text(self.paths.review_board, approved_board())
        max_steps = 50

        for _ in range(max_steps):
            state = load_run_state(self.paths)
            if state.phase == RunPhase.ARCHIVE_READY:
                return state
            result = advance(self.repo, self.adapters)
            if result.exit_code in {11, 20}:
                self._complete_host_actions(result)
                continue
            if result.exit_code == 10:
                write_text(self.paths.review_board, approved_board())
                continue
            if result.exit_code == 0 and state.phase == RunPhase.IMPLEMENTATION:
                impl = load_implementation(self.paths)
                if impl is None:
                    actions = load_actions(self.paths) if self.paths.actions.exists() else []
                    impl_action = next(
                        (
                            item
                            for item in actions
                            if item.kind == ActionKind.CURSOR_AGENT_UI
                            and item.status == ActionStatus.PENDING
                        ),
                        None,
                    )
                    if impl_action is not None:
                        output = self.repo / impl_action.output_path
                        write_text(output, "implementation done\n")
                        run_complete(
                            type("Args", (), {
                                "repo": self.repo,
                                "action_id": impl_action.id,
                                "output": output,
                            })()
                        )
                continue
            if result.exit_code != 0:
                self.fail(f"unexpected exit {result.exit_code} at phase {state.phase}")

        self.fail("workflow did not reach archive_ready")

    def test_full_flow_reaches_archive_ready_without_commit(self):
        final_state = self._drive_to_archive_ready()
        self.assertEqual(final_state.phase, RunPhase.ARCHIVE_READY)
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertNotIn(".spoon/", status.stdout)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(head.returncode, 0)

    def test_restart_resumes_from_run_state(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        saved = load_run_state(self.paths)
        result = advance(self.repo, self.adapters)
        self.assertEqual(load_run_state(self.paths).run_id, saved.run_id)
        self.assertIn(result.exit_code, {0, 11, 20})

    def test_claude_unavailable_falls_back_to_manual(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        advance(self.repo, self.adapters)
        result = advance(self.repo, {"claude_review": TimeoutAdapter()})
        self.assertEqual(result.exit_code, 20)
        self.assertTrue(result.actions)
        self.assertEqual(result.actions[0].kind, ActionKind.MANUAL)

    def test_corrupt_actions_stops_with_exit_21(self):
        advance(self.repo, self.adapters)
        self.paths.actions.write_text("{bad", encoding="utf-8")
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 21)
        self.assertEqual(result.state.status, RunStatus.FAILED)

    def test_duplicate_complete_is_idempotent_queue(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        advance(self.repo, self.adapters)
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 11)
        self.assertTrue(result.actions)
        action = result.actions[0]
        output = self.repo / action.output_path
        write_text(output, "## Verdict\n\napproved\n\n## Summary\n\nok\n")
        args = type("Args", (), {"repo": self.repo, "action_id": action.id, "output": output})()
        self.assertEqual(run_complete(args), 0)
        self.assertEqual(run_complete(args), 0)
        missing = run_complete(
            type("Args", (), {
                "repo": self.repo,
                "action_id": "missing-id",
                "output": output,
            })()
        )
        self.assertEqual(missing, 2)

    def test_all_pending_actions_failed_stops_runner(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        advance(self.repo, self.adapters)
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 11)
        for action in result.actions:
            from spoon.commands.action_cmd import run_fail

            run_fail(
                type("Args", (), {
                    "repo": self.repo,
                    "action_id": action.id,
                    "message": "blocked",
                })()
            )
        stopped = advance(self.repo, self.adapters)
        self.assertEqual(stopped.exit_code, 21)
        self.assertEqual(stopped.state.status, RunStatus.FAILED)

    def test_missing_output_rejected(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        advance(self.repo, self.adapters)
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 11)
        self.assertTrue(result.actions)
        action = result.actions[0]
        code = run_complete(
            type("Args", (), {
                "repo": self.repo,
                "action_id": action.id,
                "output": self.repo / action.output_path,
            })()
        )
        self.assertEqual(code, 2)

    def test_deleted_actions_rebuilds_queue(self):
        self._adopt_plan()
        advance(self.repo, self.adapters)
        advance(self.repo, self.adapters)
        if self.paths.actions.exists():
            self.paths.actions.unlink()
        result = advance(self.repo, self.adapters)
        self.assertIn(result.exit_code, {11, 20})
        self.assertTrue(self.paths.actions.exists())


if __name__ == "__main__":
    unittest.main()
