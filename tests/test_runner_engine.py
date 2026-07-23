import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.adapters.base import AdapterRequest, AdapterResult, AdapterStatus
from spoon.commands.adopt_plan_cmd import adopt_plan
from spoon.commands.init_cmd import create_current_layout
from spoon.constants import GENERATED_END, GENERATED_START
from spoon.git_util import current_head_or_empty
from spoon.io_util import write_text
from spoon.paths import project_paths
from spoon.runner.actions import fail_action
from spoon.runner.engine import advance, expected_actions
from spoon.runner.model import ActionKind, RunPhase, RunState, RunStatus, utc_now_iso
from spoon.runner.state_store import save_run_state


class FakeClaudeAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        output = Path(request.working_directory) / request.output_path
        output.parent.mkdir(parents=True, exist_ok=True)
        write_text(
            output,
            "## Verdict\n\napproved\n\n## Summary\n\nok\n",
        )
        return AdapterResult(status=AdapterStatus.SUCCESS, message="ok")


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


class TimeoutAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        return AdapterResult(status=AdapterStatus.UNAVAILABLE, message="timeout")


class NeedsUserAdapter:
    def execute(self, request: AdapterRequest) -> AdapterResult:
        return AdapterResult(status=AdapterStatus.NEEDS_USER, message="need approval")


class RunnerEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        self.adapters = {"claude_review": FakeClaudeAdapter()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_brief_advances_to_plan_adoption(self):
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.state.phase, RunPhase.PLAN_ADOPTION)

    def test_plan_adoption_waits_for_plan(self):
        advance(self.repo, self.adapters)
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 11)
        self.assertEqual(result.state.phase, RunPhase.PLAN_ADOPTION)
        self.assertEqual(result.actions[0].kind, ActionKind.CURSOR_PLAN_UI)

    def test_plan_adoption_advances_when_plan_exists(self):
        advance(self.repo, self.adapters)
        source = self.repo / "cursor.plan.md"
        source.write_text("# Plan\n\nDo the thing.\n", encoding="utf-8")
        adopt_plan(self.repo, source, replace=False)
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.state.phase, RunPhase.PLAN_REVIEW)

    def test_plan_review_does_not_duplicate_actions(self):
        advance(self.repo, self.adapters)
        source = self.repo / "cursor.plan.md"
        source.write_text("# Plan\n\nDo the thing.\n", encoding="utf-8")
        adopt_plan(self.repo, source, replace=False)
        advance(self.repo, self.adapters)
        first = advance(self.repo, self.adapters)
        second = advance(self.repo, self.adapters)
        self.assertEqual(first.exit_code, 11)
        self.assertEqual(second.exit_code, 11)
        self.assertEqual(len(first.actions), len(second.actions))

    def test_corrupt_actions_returns_exit_21(self):
        advance(self.repo, self.adapters)
        self.paths.actions.write_text("{bad", encoding="utf-8")
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 21)
        self.assertEqual(result.state.status, RunStatus.FAILED)

    def _reach_plan_review(self):
        advance(self.repo, self.adapters)
        source = self.repo / "cursor.plan.md"
        source.write_text("# Plan\n\nDo the thing.\n", encoding="utf-8")
        adopt_plan(self.repo, source, replace=False)
        advance(self.repo, self.adapters)

    def test_code_review_claude_unavailable_returns_exit_20(self):
        self._reach_plan_review()
        result = advance(self.repo, {"claude_review": TimeoutAdapter()})
        self.assertEqual(result.exit_code, 20)
        self.assertEqual(result.actions[0].kind, ActionKind.MANUAL)

    def test_adapter_needs_user_returns_exit_10(self):
        self._reach_plan_review()
        result = advance(self.repo, {"claude_review": NeedsUserAdapter()})
        self.assertEqual(result.exit_code, 10)
        self.assertEqual(result.state.status, RunStatus.NEEDS_USER)
        self.assertIn("need approval", result.state.pending_decision or "")

    def test_failed_actions_stop_advance(self):
        self._reach_plan_review()
        result = advance(self.repo, self.adapters)
        self.assertEqual(result.exit_code, 11)
        action = result.actions[0]
        fail_action(self.paths, action.id, "blocked")
        stopped = advance(self.repo, self.adapters)
        self.assertEqual(stopped.exit_code, 21)
        self.assertEqual(stopped.state.phase, RunPhase.PLAN_REVIEW)
        self.assertEqual(stopped.state.status, RunStatus.FAILED)

    def test_plan_decision_records_implementation_base(self):
        save_run_state(
            self.paths,
            RunState(
                schema_version=1,
                run_id="run-test",
                phase=RunPhase.PLAN_DECISION,
                status=RunStatus.READY,
                pending_decision=None,
                last_error=None,
                updated_at=utc_now_iso(),
            ),
        )
        for name in ("codex-plan.md", "claude-plan.md", "final-plan-review.md"):
            write_text(self.paths.reviews / name, "## Verdict\n\napproved\n")
        write_text(self.paths.review_board, approved_board())

        result = advance(self.repo, self.adapters)

        self.assertEqual(result.state.phase, RunPhase.IMPLEMENTATION)
        self.assertEqual(
            self.paths.implementation_base.read_text(encoding="utf-8").strip(),
            current_head_or_empty(self.repo),
        )

    def test_expected_implementation_action_reads_base_without_writing_it(self):
        state = RunState(
            schema_version=1,
            run_id="run-test",
            phase=RunPhase.IMPLEMENTATION,
            status=RunStatus.READY,
            pending_decision=None,
            last_error=None,
            updated_at=utc_now_iso(),
        )

        actions = expected_actions(state, self.repo)

        self.assertFalse(self.paths.implementation_base.exists())
        self.assertEqual(actions[0].payload["implementation_base_sha"], current_head_or_empty(self.repo))

    def test_codex_adapter_runs_in_process_when_registered(self):
        self._reach_plan_review()

        class FakeCodexAdapter:
            def execute(self, request):
                output = Path(request.working_directory) / request.output_path
                write_text(
                    output,
                    "## Verdict\n\napproved\n\n## Summary\n\nok\n\n"
                    "## Findings\n\n### Optional\n\n- _None._\n",
                )
                return AdapterResult(status=AdapterStatus.SUCCESS, message="ok")

        adapters = {
            **self.adapters,
            "codex_thread_message": FakeCodexAdapter(),
        }
        result = advance(self.repo, adapters)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue((self.paths.reviews / "codex-plan.md").is_file())


if __name__ == "__main__":
    unittest.main()
