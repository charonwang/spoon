import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.handoff_cmd import extract_accepted_for_handoff, generate_handoff
from spoon.commands.init_cmd import create_current_layout


class HandoffCommandTests(unittest.TestCase):
    def test_extract_accepted_only(self):
        board = (
            "## Decisions\n\n"
            "### Accepted For Handoff\n\n"
            "- Fix accepted item.\n\n"
            "### Parked\n\n"
            "- Do not include.\n\n"
            "### Rejected\n\n"
        )
        self.assertEqual(extract_accepted_for_handoff(board).strip(), "- Fix accepted item.")

    def test_extract_stops_at_generated_marker_when_optional_sections_are_missing(self):
        board = (
            "### Accepted For Handoff\n\n"
            "- Fix accepted item.\n\n"
            "<!-- spoon:generated-findings:start -->\n"
            "generated\n"
        )
        self.assertEqual(extract_accepted_for_handoff(board), "- Fix accepted item.")

    def test_extract_keeps_nested_details_until_real_section_boundary(self):
        board = (
            "### Accepted For Handoff\n\n"
            "### Details\n\n"
            "- Explain the accepted item.\n\n"
            "- Fix accepted item.\n\n"
            "### Parked\n\n"
            "- Do not include.\n"
        )
        self.assertEqual(
            extract_accepted_for_handoff(board).strip(),
            "### Details\n\n- Explain the accepted item.\n\n- Fix accepted item.",
        )

    def test_generate_handoff_uses_only_accepted_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.write_text(
                "# Review Board\n\n"
                "## Decisions\n\n"
                "### Accepted For Handoff\n\n"
                "- Implement route test.\n\n"
                "### Parked\n\n"
                "- Park naming cleanup.\n\n"
                "### Rejected\n\n",
                encoding="utf-8",
            )

            generate_handoff(repo)

            text = (repo / ".spoon" / "current" / "handoff.md").read_text(encoding="utf-8")
            self.assertIn("- Implement route test.", text)
            self.assertNotIn("Park naming cleanup", text)
            self.assertIn("Only implement the items below.", text)

    def test_generate_handoff_bootstraps_missing_review_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.unlink()

            generate_handoff(repo)

            self.assertTrue(board.exists())
            text = (repo / ".spoon" / "current" / "handoff.md").read_text(encoding="utf-8")
            self.assertIn("_No approved changes yet._", text)

    def test_generate_handoff_documents_plan_checkboxes_and_checkpoint_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            generate_handoff(repo)

            text = (repo / ".spoon" / "current" / "handoff.md").read_text(encoding="utf-8")
            self.assertIn("only check existing checkbox items in plan.md", text)
            self.assertIn("Do not add checklist items", text)
            self.assertIn("After relevant verification passes", text)
            self.assertIn("local checkpoint commit", text)
            self.assertIn("Stage only files for that batch", text)
            self.assertIn("Do not rewrite history, squash, or push", text)


if __name__ == "__main__":
    unittest.main()
