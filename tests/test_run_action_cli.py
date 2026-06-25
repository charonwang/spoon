import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from spoon.commands.action_cmd import run_complete, run_fail, run_list
from spoon.commands.init_cmd import run as init_run
from spoon.commands.run_cmd import run as run_cmd
from spoon.io_util import write_text
from spoon.paths import project_paths
from spoon.runner.actions import action_id, complete_action, enqueue_action, load_actions
from spoon.runner.model import (
    ActionKind,
    ActionStatus,
    ImplementationRecord,
    RunPhase,
    WorkflowAction,
    utc_now_iso,
)
from spoon.runner.state_store import load_implementation


class RunActionCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        init_run(Namespace(repo=self.repo))
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def _implementation_action(self) -> WorkflowAction:
        now = utc_now_iso()
        prompt = ".spoon/current/prompts/cursor-implement.md"
        output = ".spoon/current/implementation-summary.md"
        return WorkflowAction(
            id=action_id("run-test", RunPhase.IMPLEMENTATION.value, ActionKind.CURSOR_AGENT_UI.value, prompt, output),
            kind=ActionKind.CURSOR_AGENT_UI,
            status=ActionStatus.PENDING,
            prompt_path=prompt,
            output_path=output,
            working_directory=str(self.repo),
            payload={"phase": "implementation"},
            attempts=0,
            created_at=now,
            updated_at=now,
        )

    def test_run_json_output_shape(self):
        code = run_cmd(Namespace(repo=self.repo, continue_run=False, json=True))
        self.assertEqual(code, 0)
        # second call should still emit json keys through advance

    def test_continue_requires_existing_state(self):
        self.paths.run_state.unlink(missing_ok=True)
        code = run_cmd(Namespace(repo=self.repo, continue_run=True, json=False))
        self.assertEqual(code, 2)

    def test_action_complete_rejects_path_traversal(self):
        action = self._implementation_action()
        enqueue_action(self.paths, action)
        outside = self.repo.parent / "outside.md"
        write_text(outside, "nope\n")
        code = run_complete(
            Namespace(
                repo=self.repo,
                action_id=action.id,
                output=Path("..") / self.repo.name / "outside.md",
            )
        )
        self.assertEqual(code, 2)

    def test_implementation_complete_writes_implementation_json(self):
        action = self._implementation_action()
        enqueue_action(self.paths, action)
        output = self.paths.current / "implementation-summary.md"
        write_text(output, "done\n")
        code = run_complete(
            Namespace(repo=self.repo, action_id=action.id, output=output)
        )
        self.assertEqual(code, 0)
        record = load_implementation(self.paths)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.action_id, action.id)
        self.assertEqual(record.status, "reported_complete")

    def test_review_complete_does_not_write_implementation_json(self):
        now = utc_now_iso()
        prompt = ".spoon/current/prompts/claude-plan-review.md"
        output = ".spoon/current/reviews/claude-plan.md"
        action = WorkflowAction(
            id=action_id("run-test", RunPhase.PLAN_REVIEW.value, ActionKind.CLAUDE_REVIEW.value, prompt, output),
            kind=ActionKind.CLAUDE_REVIEW,
            status=ActionStatus.PENDING,
            prompt_path=prompt,
            output_path=output,
            working_directory=str(self.repo),
            payload={"phase": "plan_review"},
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        enqueue_action(self.paths, action)
        review_output = self.paths.reviews / "claude-plan.md"
        write_text(review_output, "review\n")
        code = run_complete(
            Namespace(repo=self.repo, action_id=action.id, output=review_output)
        )
        self.assertEqual(code, 0)
        self.assertIsNone(load_implementation(self.paths))

    def test_action_list_json(self):
        action = self._implementation_action()
        enqueue_action(self.paths, action)
        code = run_list(Namespace(repo=self.repo, json=True))
        self.assertEqual(code, 0)

    def test_action_fail_cli(self):
        action = self._implementation_action()
        enqueue_action(self.paths, action)
        code = run_fail(
            Namespace(repo=self.repo, action_id=action.id, message="unsafe")
        )
        self.assertEqual(code, 0)
        failed = load_actions(self.paths)[0]
        self.assertEqual(failed.status, ActionStatus.FAILED)

    def test_implementation_complete_rolls_back_when_marker_write_fails(self):
        action = self._implementation_action()
        enqueue_action(self.paths, action)
        output = self.paths.current / "implementation-summary.md"
        write_text(output, "done\n")
        record = ImplementationRecord(
            schema_version=1,
            status="reported_complete",
            action_id=action.id,
            completed_at=utc_now_iso(),
            summary_path=action.output_path or "",
        )
        with patch("spoon.runner.state_store.save_implementation", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                complete_action(self.paths, action.id, output, implementation_record=record)
        stored = load_actions(self.paths)[0]
        self.assertEqual(stored.status, ActionStatus.PENDING)
        self.assertIsNone(load_implementation(self.paths))


if __name__ == "__main__":
    unittest.main()
