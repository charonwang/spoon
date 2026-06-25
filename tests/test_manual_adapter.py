import unittest

from spoon.adapters.base import AdapterRequest, AdapterStatus
from spoon.adapters.manual import ManualAdapter
from spoon.runner.model import ActionKind


class ManualAdapterTests(unittest.TestCase):
    def test_manual_adapter_needs_host_with_complete_command(self):
        request = AdapterRequest(
            action_id="abc123",
            prompt_path=".spoon/current/prompts/codex-plan-review.md",
            output_path=".spoon/current/reviews/codex-plan.md",
            working_directory="D:/repo",
        )
        result = ManualAdapter().execute(request)
        self.assertEqual(result.status, AdapterStatus.NEEDS_HOST)
        self.assertIsNotNone(result.action)
        assert result.action is not None
        self.assertEqual(result.action.kind, ActionKind.MANUAL)
        instructions = str(result.action.payload["instructions"])
        self.assertIn(request.prompt_path, instructions)
        self.assertIn(request.output_path, instructions)
        self.assertIn("spoon action complete --id abc123", instructions)
        self.assertIn("--output .spoon/current/reviews/codex-plan.md", instructions)


if __name__ == "__main__":
    unittest.main()
