import unittest

from spoon.runner.model import (
    ActionKind,
    ActionStatus,
    ImplementationRecord,
    RunPhase,
    RunState,
    RunStatus,
    WorkflowAction,
)


class RunnerModelTests(unittest.TestCase):
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
        restored = RunState.from_dict(state.to_dict())
        self.assertEqual(restored, state)

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
        )
        self.assertEqual(record.to_dict()["status"], "reported_complete")


if __name__ == "__main__":
    unittest.main()
