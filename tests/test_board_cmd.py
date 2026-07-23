import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.board_cmd import generate_board
from spoon.commands.init_cmd import create_current_layout
from spoon.constants import GENERATED_END, GENERATED_START
from spoon.review_parser import classify_review_text


class BoardCommandTests(unittest.TestCase):
    def test_board_reads_reviews_and_preserves_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.write_text(
                "# Review Board\n\n"
                "## Decisions\n\n"
                "### Accepted For Handoff\n\n"
                "- Keep this decision.\n\n"
                "### Parked\n\n"
                "### Rejected\n\n"
                "<!-- spoon:generated-findings:start -->\nold\n<!-- spoon:generated-findings:end -->\n",
                encoding="utf-8",
            )
            review = repo / ".spoon" / "current" / "reviews" / "codex-plan.md"
            review.write_text(
                "## Blocking\n\n- P1: Fix route test.\n\n## Test Gaps\n\n- Add real route test.\n",
                encoding="utf-8",
            )

            generate_board(repo)

            text = board.read_text(encoding="utf-8")
            self.assertIn("- Keep this decision.", text)
            self.assertIn("### Blocking", text)
            self.assertIn("[codex-plan.md] P1: Fix route test.", text)
            self.assertIn("### Test Gaps", text)
            self.assertNotIn("old", text)

    def test_board_repairs_missing_generated_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.write_text(
                "# Review Board\n\n"
                "## Decisions\n\n"
                "### Accepted For Handoff\n\n"
                "- Keep accepted item.\n",
                encoding="utf-8",
            )
            review = repo / ".spoon" / "current" / "reviews" / "codex-code.md"
            review.write_text("## Blocking\n\n- P1: Fix staged diff.\n", encoding="utf-8")

            generate_board(repo)

            text = board.read_text(encoding="utf-8")
            self.assertIn("- Keep accepted item.", text)
            self.assertIn("<!-- spoon:generated-findings:start -->", text)
            self.assertIn("<!-- spoon:generated-findings:end -->", text)
            self.assertIn("[codex-code.md] P1: Fix staged diff.", text)

    def test_board_removes_stale_generated_text_after_single_start_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.write_text(
                "# Review Board\n\n"
                "## Decisions\n\n"
                "### Accepted For Handoff\n\n"
                "- Keep accepted item.\n\n"
                f"{GENERATED_START}\n"
                "stale generated finding\n",
                encoding="utf-8",
            )
            review = repo / ".spoon" / "current" / "reviews" / "codex-code.md"
            review.write_text("## Blocking\n\n- P1: Fresh finding.\n", encoding="utf-8")

            generate_board(repo)

            text = board.read_text(encoding="utf-8")
            self.assertIn("- Keep accepted item.", text)
            self.assertIn("[codex-code.md] P1: Fresh finding.", text)
            self.assertNotIn("stale generated finding", text)

    def test_board_removes_stale_generated_text_after_reversed_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            board = repo / ".spoon" / "current" / "review-board.md"
            board.write_text(
                "# Review Board\n\n"
                "## Decisions\n\n"
                "### Accepted For Handoff\n\n"
                "- Keep accepted item.\n\n"
                f"{GENERATED_END}\n"
                "stale reversed finding\n"
                f"{GENERATED_START}\n",
                encoding="utf-8",
            )
            review = repo / ".spoon" / "current" / "reviews" / "codex-code.md"
            review.write_text("## Blocking\n\n- P1: Fresh reversed finding.\n", encoding="utf-8")

            generate_board(repo)

            text = board.read_text(encoding="utf-8")
            self.assertIn("- Keep accepted item.", text)
            self.assertIn("[codex-code.md] P1: Fresh reversed finding.", text)
            self.assertNotIn("stale reversed finding", text)

    def test_board_ignores_non_markdown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            (repo / ".spoon" / "current" / "reviews" / "notes.txt").write_text(
                "P1 hidden\n",
                encoding="utf-8",
            )

            generate_board(repo)

            text = (repo / ".spoon" / "current" / "review-board.md").read_text(encoding="utf-8")
            self.assertNotIn("hidden", text)

    def test_board_preserves_multiline_finding_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)
            review = repo / ".spoon" / "current" / "reviews" / "codex-code.md"
            review.write_text(
                "## Findings\n\n"
                "- Severity: P1\n"
                "  File: app.py\n"
                "  Line: 12\n"
                "  Problem: unsafe state transition\n",
                encoding="utf-8",
            )

            generate_board(repo)

            text = (repo / ".spoon" / "current" / "review-board.md").read_text(encoding="utf-8")
            self.assertIn("Severity: P1", text)
            self.assertIn("File: app.py", text)
            self.assertIn("Problem: unsafe state transition", text)

    def test_unstructured_review_emits_parser_warning(self):
        grouped = classify_review_text("extra.md", "- investigate this\n- maybe fix that\n")
        self.assertTrue(any("[PARSER WARNING]" in item for item in grouped["Needs Triage"]))

    def test_summary_heading_ignores_bullets_then_later_sections_work(self):
        grouped = classify_review_text(
            "summary.md",
            "## Summary:\n"
            "- ignore this note\n\n"
            "## Blocking\n"
            "- P1: Fix route test.\n",
        )

        all_items = [item for items in grouped.values() for item in items]
        self.assertFalse(any("ignore this note" in item for item in all_items))
        self.assertTrue(any("P1: Fix route test." in item for item in grouped["Blocking"]))

    def test_hash_number_line_does_not_reset_current_group(self):
        grouped = classify_review_text(
            "issue.md",
            "## Blocking\n"
            "#123\n"
            "- P1: Fix route test.\n",
        )

        self.assertTrue(any("P1: Fix route test." in item for item in grouped["Blocking"]))
        self.assertTrue(any("#123" in item for item in grouped["Needs Triage"]))
        self.assertFalse(any("Fix route test." in item for item in grouped["Needs Triage"]))

    def test_unparsed_content_is_split_by_heading(self):
        grouped = classify_review_text(
            "mixed.md",
            "## Blocking\n"
            "plain blocking note\n"
            "## Optional\n"
            "plain optional note\n",
        )

        warnings = [item for item in grouped["Needs Triage"] if "[PARSER WARNING]" in item]
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("plain blocking note" in item for item in warnings))
        self.assertTrue(any("plain optional note" in item for item in warnings))
        self.assertFalse(any("plain blocking note | plain optional note" in item for item in warnings))

    def test_no_blockers_sentinel_is_not_parser_warning(self):
        grouped = classify_review_text(
            "claude-plan.md",
            "## Blocking\n"
            "No blockers, ready for implementation.\n"
            "## Should Fix\n"
            "- [SUGGEST] tighten the guard.\n",
        )

        warnings = [item for item in grouped["Needs Triage"] if "[PARSER WARNING]" in item]
        self.assertEqual(warnings, [])
        self.assertTrue(any("tighten the guard." in item for item in grouped["Should Fix"]))

    def test_subheading_findings_are_captured_under_group(self):
        grouped = classify_review_text(
            "claude-plan.md",
            "## Should Fix\n"
            "### S1: link format\n"
            "plan.md uses windows paths.\n\n"
            "## Optional\n"
            "### N1: add fuzz\n"
            "follow up later.\n",
        )

        warnings = [item for item in grouped["Needs Triage"] if "[PARSER WARNING]" in item]
        self.assertEqual(warnings, [])
        self.assertTrue(any("S1: link format" in item for item in grouped["Should Fix"]))
        self.assertTrue(any("windows paths" in item for item in grouped["Should Fix"]))
        self.assertTrue(any("N1: add fuzz" in item for item in grouped["Optional"]))

    def test_changes_requested_with_space_is_not_unparsed_noise(self):
        grouped = classify_review_text(
            "verdict.md",
            "## Blocking\n"
            "Changes Requested\n"
            "- P1: Fix route test.\n",
        )

        warnings = [item for item in grouped["Needs Triage"] if "[PARSER WARNING]" in item]
        self.assertEqual(warnings, [])
        self.assertTrue(any("P1: Fix route test." in item for item in grouped["Blocking"]))


if __name__ == "__main__":
    unittest.main()
