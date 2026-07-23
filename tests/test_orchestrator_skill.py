from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "spoon"
SKILL_MD = SKILL_ROOT / "SKILL.md"
ACTION_KINDS = SKILL_ROOT / "references" / "action-kinds.md"
DECISION_GATES = SKILL_ROOT / "references" / "decision-gates.md"

FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
CASELESS = re.IGNORECASE
CASELESS_DOTALL = re.IGNORECASE | re.DOTALL


def read_skill_bundle() -> dict[str, str]:
    return {
        "skill": SKILL_MD.read_text(encoding="utf-8"),
        "action_kinds": ACTION_KINDS.read_text(encoding="utf-8"),
        "decision_gates": DECISION_GATES.read_text(encoding="utf-8"),
    }


def combined_text(bundle: dict[str, str]) -> str:
    return "\n".join(bundle.values())


class OrchestratorSkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = read_skill_bundle()
        self.all_text = combined_text(self.bundle)
        self.skill = self.bundle["skill"]

    def test_required_files_exist(self) -> None:
        self.assertTrue(SKILL_MD.is_file())
        self.assertTrue(ACTION_KINDS.is_file())
        self.assertTrue(DECISION_GATES.is_file())

    def test_skill_frontmatter_names_spoon(self) -> None:
        match = FRONTMATTER_RE.match(self.skill)
        self.assertIsNotNone(match)
        assert match is not None
        frontmatter = match.group("body")
        self.assertIn("name: spoon", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertIn("/spoon", frontmatter)

    def test_loop_documents_spoon_run_json(self) -> None:
        self.assertIn("spoon run --repo <repo> --json", self.skill)
        self.assertIn("exit_code", self.skill)
        self.assertIn("pending_decision", self.skill)

    def test_startup_auto_inits_and_requires_config_confirm(self) -> None:
        self.assertIn("spoon init", self.skill)
        self.assertIn("spoon config show", self.skill)
        self.assertIn("spoon config ack", self.skill)
        self.assertIn("Confirmation:", self.skill)
        self.assertRegex(
            self.skill,
            re.compile(
                r"Confirmation: needed|needed \(\.\.\.\)",
                CASELESS,
            ),
        )
        self.assertRegex(
            self.skill,
            re.compile(
                r"Before confirmation.*do \*\*not\*\*|do \*\*not\*\*.*spoon run",
                CASELESS_DOTALL,
            ),
        )
        self.assertRegex(
            self.skill,
            re.compile(
                r"do \*\*not\*\* repeat the config confirmation",
                CASELESS,
            ),
        )
        self.assertRegex(
            self.skill,
            re.compile(
                r"Never paste the raw|/spoon.*Goal|distill.*intent|PRD.*title|title.*PRD",
                CASELESS_DOTALL,
            ),
        )
        self.assertRegex(
            self.skill,
            re.compile(r"Goal first line", CASELESS),
        )

    def test_exit_codes_documented(self) -> None:
        for code in ("0", "10", "11", "20", "21"):
            self.assertRegex(self.skill, rf"\b{code}\b")

    def test_exit_code_semantics_mapped(self) -> None:
        self.assertRegex(
            self.skill,
            re.compile(
                r"`20`.*manual|manual fallback.*`20`|Adapter unavailable.*manual",
                CASELESS_DOTALL,
            ),
        )
        self.assertRegex(
            self.skill,
            re.compile(
                r"`21`.*Runner failure|Runner failure.*\*\*stop\*\*", CASELESS_DOTALL),
        )

    def test_host_action_completion_commands_documented(self) -> None:
        self.assertIn("spoon action complete --id", self.all_text)
        self.assertIn("spoon action fail --id", self.all_text)

    def test_skill_is_stateless(self) -> None:
        self.assertRegex(
            self.skill,
            re.compile(r"holds \*\*no state\*\*|no state", CASELESS),
        )

    def test_forbidden_superpowers(self) -> None:
        self.assertRegex(
            self.skill,
            re.compile(r"Do not use Superpowers", CASELESS),
        )

    def test_forbidden_auto_commit(self) -> None:
        self.assertNotRegex(self.all_text, re.compile(
            r"git\s+commit", CASELESS))
        self.assertNotRegex(self.all_text, re.compile(r"git\s+push", CASELESS))
        lowered = self.all_text.lower()
        self.assertNotIn("auto-commit", lowered)
        self.assertNotIn("autocommit", lowered)

    def test_forbidden_direct_actions_json_edit(self) -> None:
        self.assertRegex(
            self.skill,
            r"Do not edit `actions\.json`",
        )

    def test_forbidden_create_or_downgrade_manual(self) -> None:
        lowered = self.all_text.lower()
        self.assertNotIn("create a manual", lowered)
        self.assertNotIn("create a `manual`", lowered)
        self.assertNotIn("downgrade to manual", lowered)
        self.assertNotIn("keep or create", lowered)

    def test_forbidden_review_board_decision_rewrite(self) -> None:
        self.assertRegex(
            self.all_text,
            re.compile(
                r"Do not rewrite human `Decisions`|do not edit Generated Findings or\s+Decisions",
                CASELESS_DOTALL,
            ),
        )

    def test_cursor_ui_disabled_by_default(self) -> None:
        self.assertIn("experimental_cursor_ui", self.all_text)
        self.assertRegex(
            self.all_text,
            re.compile(
                r"experimental_cursor_ui.*false|off by default|Manual by default",
                CASELESS_DOTALL,
            ),
        )

    def test_codex_never_auto_creates_threads_when_desktop_disabled(self) -> None:
        self.assertIn(
            "Never auto-create a new Codex thread when both `agents.codex.cli` and `agents.codex.desktop` are false",
            self.bundle["action_kinds"],
        )

    def test_paths_not_full_bodies(self) -> None:
        self.assertRegex(
            self.all_text,
            re.compile(
                r"Never paste full|paths plus brief instructions|file paths and short instructions",
                CASELESS,
            ),
        )

    def test_working_directory_must_match_repo(self) -> None:
        self.assertRegex(
            self.all_text,
            re.compile(
                r"working_directory.*match.*repo|working_directory does not match target repo",
                CASELESS_DOTALL,
            ),
        )

    def test_complete_uses_declared_output_path(self) -> None:
        action_kinds = self.bundle["action_kinds"]
        self.assertNotIn("--output .spoon/current/plan.md", action_kinds)
        self.assertNotIn(
            "--output .spoon/current/implementation-summary.md",
            action_kinds,
        )
        self.assertGreaterEqual(
            action_kinds.count("--output <output_path>"), 3)

    def test_action_kinds_cover_host_kinds(self) -> None:
        text = self.bundle["action_kinds"]
        for kind in (
            "codex_thread_message",
            "cursor_plan_ui",
            "cursor_agent_ui",
            "manual",
        ):
            self.assertIn(f"`{kind}`", text)
        self.assertIn("`claude_review`", text)
        self.assertIn("Not a host action", text)

    def test_decision_gates_cover_all_gates(self) -> None:
        text = self.bundle["decision_gates"]
        for gate in (
            "plan_review_gate",
            "code_review_gate",
            "implementation_gate",
            "final_check_gate",
        ):
            self.assertIn(f"`{gate}`", text)

    def test_references_linked_from_skill(self) -> None:
        self.assertIn("references/action-kinds.md", self.skill)
        self.assertIn("references/decision-gates.md", self.skill)

    def test_claude_review_delegated_to_runner(self) -> None:
        self.assertRegex(
            self.skill,
            r"Skip `claude_review`|ClaudeCliAdapter.*inside `spoon run`",
        )


if __name__ == "__main__":
    unittest.main()
