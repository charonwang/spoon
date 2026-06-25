import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.board_cmd import generate_board
from spoon.commands.init_cmd import create_current_layout
from spoon.constants import GENERATED_END, GENERATED_START
from spoon.io_util import write_text
from spoon.paths import project_paths
from spoon.runner.gates import (
    code_review_gate,
    final_check_gate,
    implementation_gate,
    plan_review_gate,
    section_items,
)


def board_with_generated(blocking: list[str], triage: list[str]) -> str:
    def section(name: str, items: list[str]) -> str:
        lines = [f"### {name}", ""]
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("_None._")
        lines.append("")
        return "\n".join(lines)

    generated = "\n".join(
        [
            "## Generated Findings",
            "",
            section("Blocking", blocking),
            section("Should Fix", []),
            section("Optional", []),
            section("Test Gaps", []),
            section("Needs Triage", triage),
        ]
    )
    return (
        "# Review Board\n\n"
        "## Decisions\n\n"
        "### Accepted For Handoff\n\n"
        "- Add route test.\n\n"
        f"{GENERATED_START}\n{generated}{GENERATED_END}\n"
    )


class RunnerGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_sections_do_not_block(self):
        write_text(self.paths.review_board, board_with_generated([], []))
        for name in ("codex-plan.md", "claude-plan.md", "final-plan-review.md"):
            write_text(self.paths.reviews / name, "## Verdict\n\napproved\n")
        result = plan_review_gate(self.paths)
        self.assertTrue(result.ready)
        self.assertFalse(result.needs_user)

    def test_blocking_items_need_user(self):
        write_text(self.paths.reviews / "codex-plan.md", "## Blocking\n\n- P1: fix it\n")
        write_text(self.paths.reviews / "claude-plan.md", "## Verdict\n\napproved\n")
        write_text(self.paths.reviews / "final-plan-review.md", "## Verdict\n\napproved\n")
        result = plan_review_gate(self.paths)
        self.assertFalse(result.ready)
        self.assertTrue(result.needs_user)

    def test_conflict_goes_to_triage_via_board_generation(self):
        write_text(self.paths.reviews / "codex-plan.md", "- [CONFLICT] two plans\n")
        write_text(self.paths.reviews / "claude-plan.md", "## Verdict\n\napproved\n")
        write_text(self.paths.reviews / "final-plan-review.md", "## Verdict\n\napproved\n")
        generate_board(self.repo)
        board_text = self.paths.review_board.read_text(encoding="utf-8")
        triage = section_items(board_text, "Needs Triage")
        self.assertTrue(any("[CONFLICT]" in item for item in triage))
        result = plan_review_gate(self.paths)
        self.assertFalse(result.ready)
        self.assertTrue(result.needs_user)

    def test_decisions_section_is_not_scanned_for_blocking(self):
        write_text(
            self.paths.review_board,
            "# Review Board\n\n"
            "## Decisions\n\n"
            "### Accepted For Handoff\n\n"
            "- P1: this is a human note, not a generated finding.\n\n"
            f"{GENERATED_START}\n"
            "## Generated Findings\n\n"
            "### Blocking\n\n"
            "_None._\n\n"
            "### Should Fix\n\n"
            "_None._\n\n"
            "### Optional\n\n"
            "_None._\n\n"
            "### Test Gaps\n\n"
            "_None._\n\n"
            "### Needs Triage\n\n"
            "_None._\n"
            f"{GENERATED_END}\n",
        )
        for name in ("codex-plan.md", "claude-plan.md", "final-plan-review.md"):
            write_text(self.paths.reviews / name, "## Verdict\n\napproved\n")
        result = plan_review_gate(self.paths)
        self.assertTrue(result.ready)

    def test_implementation_gate_requires_accepted_handoff(self):
        write_text(self.paths.review_board, board_with_generated([], []))
        result = implementation_gate(self.paths)
        self.assertFalse(result.ready)
        self.assertTrue(result.needs_user)

    def test_final_check_gate_blocks_on_should_fix(self):
        write_text(self.paths.reviews / "codex-code.md", "## Should Fix\n\n- P2: follow up\n")
        write_text(self.paths.reviews / "claude-code.md", "## Verdict\n\napproved\n")
        write_text(self.paths.reviews / "cursor-self-review.md", "## Verdict\n\napproved\n")
        write_text(self.paths.review_board, board_with_generated([], []))
        result = final_check_gate(self.paths)
        self.assertFalse(result.ready)
        self.assertTrue(result.needs_user)

    def test_code_review_gate_requires_reviews(self):
        result = code_review_gate(self.paths)
        self.assertFalse(result.ready)


if __name__ == "__main__":
    unittest.main()
