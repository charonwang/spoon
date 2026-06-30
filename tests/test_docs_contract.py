from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocsContractTests(unittest.TestCase):
    def test_spoon_no_commit_promises_remain_actor_scoped(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        design = (ROOT / "docs" / "design-overview.md").read_text(encoding="utf-8")
        host_actions = (ROOT / "docs" / "host-actions.md").read_text(encoding="utf-8")
        export_policy = (ROOT / "docs" / "export-policy.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills" / "spoon-orchestrator" / "SKILL.md").read_text(encoding="utf-8")
        decision_gates = (
            ROOT / "skills" / "spoon-orchestrator" / "references" / "decision-gates.md"
        ).read_text(encoding="utf-8")

        self.assertIn("It does not stage, commit, push, or modify business code.", readme)
        self.assertIn("It does not change application code, stage files, commit changes", design)
        self.assertIn("Host actions must not stage, commit, push", host_actions)
        self.assertIn("It never pushes to GitHub", export_policy)
        self.assertIn("Do not stage, commit, push", skill)
        self.assertIn("Do not commit or push repository changes.", decision_gates)

        self.assertIn("coding agent to create a local checkpoint commit", readme)
        self.assertIn("Spoon, the Runner, and host", design)
        self.assertIn("That Git rule applies to the host loop itself", host_actions)
        self.assertIn("This Git rule applies to the host loop itself", skill)
        self.assertIn("This rule applies to the host loop while paused", decision_gates)


if __name__ == "__main__":
    unittest.main()
