import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.adopt_plan_cmd import adopt_plan
from spoon.commands.board_cmd import generate_board
from spoon.commands.handoff_cmd import generate_handoff
from spoon.commands.init_cmd import create_current_layout
from spoon.commands.prompts_cmd import generate_prompts
from spoon.commands.snapshot_cmd import create_snapshot


class IntegrationFlowTests(unittest.TestCase):
    def test_v1_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            (repo / "app.txt").write_text("hello\n", encoding="utf-8")

            create_current_layout(repo)
            source_plan = Path(tmp) / "cursor.plan.md"
            source_plan.write_text(
                "# Plan\n\n"
                "Use file:///C:/path/to/your/repo/app.txt#L1\n"
                "Avoid C:\\path\\to\\bad.go:82\n",
                encoding="utf-8",
            )
            adopt_plan(repo, source_plan, replace=False)

            plan = repo / ".spoon" / "current" / "plan.md"
            plan_text = plan.read_text(encoding="utf-8")
            self.assertIn("spoon adopted-plan", plan_text)
            self.assertIn("Canonical source: .spoon/current/plan.md", plan_text)

            plan_sources = repo / ".spoon" / "current" / "snapshots" / "plan-sources.txt"
            plan_sources_text = plan_sources.read_text(encoding="utf-8")
            self.assertIn("Adopted from:", plan_sources_text)
            self.assertIn("Adopted to:", plan_sources_text)
            self.assertIn("Link warnings:", plan_sources_text)

            create_snapshot(repo, test_cmd="python --version", dependency_cmd=None)
            generate_prompts(repo)

            final_plan_review = repo / ".spoon" / "current" / "prompts" / "final-plan-review.md"
            self.assertIn(
                "file:///C:/path/to/your/repo/internal/file.go#L82",
                final_plan_review.read_text(encoding="utf-8"),
            )

            review = repo / ".spoon" / "current" / "reviews" / "codex-plan.md"
            review.write_text("## Blocking\n\n- P1: Add route test.\n", encoding="utf-8")
            generate_board(repo)

            board = repo / ".spoon" / "current" / "review-board.md"
            board_text = board.read_text(encoding="utf-8")
            self.assertIn("P1: Add route test.", board_text)
            board.write_text(
                board_text.replace(
                    "### Accepted For Handoff\n\n",
                    "### Accepted For Handoff\n\n- Add route test.\n\n### Parked\n\n- Do not ship this.\n\n",
                ),
                encoding="utf-8",
            )
            generate_handoff(repo)

            handoff = repo / ".spoon" / "current" / "handoff.md"
            handoff_text = handoff.read_text(encoding="utf-8")
            self.assertIn("- Add route test.", handoff_text)
            self.assertNotIn("P1: Add route test.", handoff_text)
            self.assertNotIn("Do not ship this.", handoff_text)
            self.assertFalse(source_plan.exists())
            self.assertIn(".spoon/", (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
