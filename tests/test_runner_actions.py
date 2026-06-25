import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands.init_cmd import create_current_layout
from spoon.io_util import write_text
from spoon.paths import project_paths
from spoon.runner.actions import (
    ActionsCorruptError,
    action_id,
    complete_action,
    enqueue_action,
    ensure_actions,
    load_actions,
    output_digest,
    rebuild_expected_actions,
)
from spoon.runner.model import ActionKind, ActionStatus, RunState, WorkflowAction, utc_now_iso


class RunnerActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)
        self.state = RunState.new("run-001")
        now = utc_now_iso()
        self.action = WorkflowAction(
            id=action_id(
                "run-001",
                "plan_review",
                ActionKind.CLAUDE_REVIEW.value,
                ".spoon/current/prompts/claude-plan-review.md",
                ".spoon/current/reviews/claude-plan.md",
            ),
            kind=ActionKind.CLAUDE_REVIEW,
            status=ActionStatus.PENDING,
            prompt_path=".spoon/current/prompts/claude-plan-review.md",
            output_path=".spoon/current/reviews/claude-plan.md",
            working_directory=str(self.repo),
            payload={"phase": "plan_review"},
            attempts=0,
            created_at=now,
            updated_at=now,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_enqueue_is_idempotent(self):
        first = enqueue_action(self.paths, self.action)
        second = enqueue_action(self.paths, self.action)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(load_actions(self.paths)), 1)

    def test_complete_requires_nonempty_output(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        output.unlink(missing_ok=True)
        with self.assertRaises(FileNotFoundError):
            complete_action(self.paths, self.action.id, output)
        write_text(output, "   ")
        with self.assertRaises(ValueError):
            complete_action(self.paths, self.action.id, output)
        write_text(output, "review body\n")
        completed = complete_action(self.paths, self.action.id, output)
        self.assertEqual(completed.status, ActionStatus.COMPLETED)

    def test_complete_rolls_back_when_event_append_fails(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        with patch("spoon.runner.actions.append_event", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                complete_action(self.paths, self.action.id, output)
        stored = load_actions(self.paths)[0]
        self.assertEqual(stored.status, ActionStatus.PENDING)
        self.assertFalse(any("action_completed" in line for line in self.paths.events.read_text(encoding="utf-8").splitlines()))

    def test_rebuild_from_missing_actions_file(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        complete_action(self.paths, self.action.id, output)
        self.paths.actions.unlink()
        rebuilt = rebuild_expected_actions(self.paths, self.state, [self.action])
        self.assertEqual([item.id for item in rebuilt], [self.action.id])
        self.assertEqual(rebuilt[0].status, ActionStatus.COMPLETED)

    def test_corrupt_actions_file_raises(self):
        self.paths.actions.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(ActionsCorruptError):
            load_actions(self.paths)
        self.assertEqual(self.paths.actions.read_text(encoding="utf-8"), "{not-json")

    def test_non_object_entry_is_corrupt(self):
        self.paths.actions.write_text("[null]\n", encoding="utf-8")
        with self.assertRaises(ActionsCorruptError):
            load_actions(self.paths)

    def test_duplicate_complete_is_idempotent(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        first = complete_action(self.paths, self.action.id, output)
        event_count = len(self.paths.events.read_text(encoding="utf-8").splitlines())
        second = complete_action(self.paths, self.action.id, output)
        self.assertEqual(first, second)
        self.assertEqual(first.attempts, 1)
        self.assertEqual(len(self.paths.events.read_text(encoding="utf-8").splitlines()), event_count)

    def test_ensure_actions_preserves_completed_from_other_phases(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        complete_action(self.paths, self.action.id, output)
        other = WorkflowAction(
            id=action_id(
                "run-001",
                "code_review",
                ActionKind.MANUAL.value,
                ".spoon/current/handoff.md",
                ".spoon/current/reviews/cursor-self-review.md",
            ),
            kind=ActionKind.MANUAL,
            status=ActionStatus.PENDING,
            prompt_path=".spoon/current/handoff.md",
            output_path=".spoon/current/reviews/cursor-self-review.md",
            working_directory=str(self.repo),
            payload={"phase": "code_review"},
            attempts=0,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        merged = ensure_actions(self.paths, self.state, [other])
        ids = {item.id for item in merged}
        self.assertIn(self.action.id, ids)
        self.assertIn(other.id, ids)
        completed = next(item for item in merged if item.id == self.action.id)
        self.assertEqual(completed.status, ActionStatus.COMPLETED)

    def test_recover_completed_without_output_path(self):
        now = utc_now_iso()
        action = WorkflowAction(
            id=action_id("run-001", "plan_adoption", ActionKind.CURSOR_PLAN_UI.value, "p", None),
            kind=ActionKind.CURSOR_PLAN_UI,
            status=ActionStatus.PENDING,
            prompt_path=".spoon/current/prompts/cursor-plan.md",
            output_path=None,
            working_directory=str(self.repo),
            payload={"phase": "plan_adoption"},
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        enqueue_action(self.paths, action)
        from spoon.runner.events import append_event

        append_event(
            self.paths,
            "action_completed",
            {"action_id": action.id, "output_path": "", "output_digest": ""},
        )
        rebuilt = rebuild_expected_actions(self.paths, self.state, [action])
        self.assertEqual(rebuilt[0].status, ActionStatus.COMPLETED)

    def test_deleted_output_recovers_pending(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        complete_action(self.paths, self.action.id, output)
        output.unlink()
        rebuilt = rebuild_expected_actions(self.paths, self.state, [self.action])
        self.assertEqual(rebuilt[0].status, ActionStatus.PENDING)

    def test_digest_mismatch_recovers_pending(self):
        enqueue_action(self.paths, self.action)
        output = self.paths.reviews / "claude-plan.md"
        write_text(output, "review body\n")
        complete_action(self.paths, self.action.id, output)
        write_text(output, "changed\n")
        rebuilt = rebuild_expected_actions(self.paths, self.state, [self.action])
        self.assertEqual(rebuilt[0].status, ActionStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
