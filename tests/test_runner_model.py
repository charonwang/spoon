import re
import unittest

from spoon.runner.model import (
    ActionKind,
    ActionStatus,
    ImplementationRecord,
    RunPhase,
    RunState,
    RunStatus,
    WorkflowAction,
    touch_state,
    utc_now_iso,
)


class RunnerModelTests(unittest.TestCase):
    def test_timestamp_has_subsecond_precision(self):
        # Snapshot-vs-completion freshness is compared with `>`; second-level
        # resolution collides on fast machines and stalls the Runner. Keep
        # fixed 6-digit microseconds so timestamps stay orderable.
        stamp = utc_now_iso()
        self.assertRegex(stamp, re.compile(r"T\d\d:\d\d:\d\d\.\d{6}\+00:00$"))

    def test_enum_round_trip(self):
        self.assertEqual(RunPhase("plan_review"), RunPhase.PLAN_REVIEW)
        self.assertEqual(RunStatus("needs_host"), RunStatus.NEEDS_HOST)
        self.assertEqual(ActionKind("claude_review"), ActionKind.CLAUDE_REVIEW)
        self.assertEqual(ActionStatus("pending"), ActionStatus.PENDING)

    def test_run_state_round_trip(self):
        state = RunState.new("run-001")
        self.assertEqual(state.schema_version, 1)
        self.assertEqual(state.run_id, "run-001")
        self.assertEqual(state.phase, RunPhase.BRIEF)
        self.assertEqual(state.status, RunStatus.READY)
        self.assertIsNone(state.task_label)
        restored = RunState.from_dict(state.to_dict())
        self.assertEqual(restored, state)

    def test_run_state_task_label_round_trip(self):
        state = touch_state(RunState.new("run-001"), task_label="ST冒烟")
        restored = RunState.from_dict(state.to_dict())
        self.assertEqual(restored.task_label, "ST冒烟")

    def test_workflow_action_round_trip(self):
        action = WorkflowAction(
            id="abc123",
            kind=ActionKind.MANUAL,
            status=ActionStatus.PENDING,
            prompt_path=".spoon/current/prompts/a.md",
            output_path=".spoon/current/reviews/a.md",
            working_directory="D:/repo",
            payload={"phase": "plan_review"},
            attempts=0,
            created_at="2026-06-19T00:00:00+00:00",
            updated_at="2026-06-19T00:00:00+00:00",
        )
        restored = WorkflowAction.from_dict(action.to_dict())
        self.assertEqual(restored, action)

    def test_implementation_record_status(self):
        record = ImplementationRecord(
            schema_version=1,
            status="reported_complete",
            action_id="abc",
            completed_at="2026-06-19T00:00:00+00:00",
            summary_path=".spoon/current/implementation-summary.md",
            base_sha="base-sha",
        )
        self.assertEqual(record.to_dict()["status"], "reported_complete")
        self.assertEqual(ImplementationRecord.from_dict(
            record.to_dict()), record)


if __name__ == "__main__":
    unittest.main()
