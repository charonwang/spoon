import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout
from spoon.commands.prompts_cmd import generate_prompts
from spoon.io_util import write_json_atomic
from spoon.paths import project_paths


class PromptCommandTests(unittest.TestCase):
    def test_generate_prompts_writes_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "final-plan-review.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("Canonical task workspace: .spoon/current/", text)
            self.assertIn(
                "file:///C:/path/to/your/repo/internal/file.go#L82",
                text,
            )
            self.assertIn("No blockers, ready for implementation.", text)
            self.assertIn("Task language:", text)

    def test_generate_prompts_honors_language_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)
            paths = project_paths(repo)
            write_json_atomic(paths.config, {"language": "ja-JP"})

            generate_prompts(repo)

            text = (paths.prompts /
                    "claude-plan-review.md").read_text(encoding="utf-8")
            self.assertIn("Task language: ja-JP", text)

    def test_generate_prompts_auto_follows_brief_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)
            paths = project_paths(repo)
            paths.brief.write_text(
                "# Brief\n\n## Goal\n\n请为 README 增加简短的中文 Usage 说明。\n",
                encoding="utf-8",
            )

            generate_prompts(repo)

            text = (paths.prompts /
                    "claude-plan-review.md").read_text(encoding="utf-8")
            self.assertIn("Task language: zh", text)

    def test_generate_final_check_prompt_uses_snapshot_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "final-check.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("snapshots/dependency-check.txt", text)
            self.assertIn("snapshots/sensitive-scan.txt", text)
            self.assertIn(
                "checkpoint commits since implementation-base.txt", text)
            self.assertIn("unstaged, staged, and untracked", text)

    def test_code_review_prompt_mentions_untracked_diff_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "codex-code-review.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("unstaged, staged, and untracked", text)
            self.assertIn(
                "checkpoint commits since implementation-base.txt", text)
            self.assertIn("status.txt", text)

    def test_commit_message_prompt_mentions_real_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "commit-message.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("snapshots/diff-stat.txt", text)
            self.assertIn("current checkpoint batch or final task", text)
            self.assertIn("describe only the staged files", text)
            self.assertIn("Do not rely on chat memory", text)

    def test_implement_prompt_allows_verified_local_checkpoints_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "cursor-implement.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn(
                "only check existing checkbox items in plan.md", text)
            self.assertIn("Do not add checklist items", text)
            self.assertIn("or explain why it cannot run", text)
            self.assertIn("After that verification passes", text)
            self.assertIn("local checkpoint commit", text)
            self.assertIn("Stage only files for that batch", text)
            self.assertIn("Do not rewrite history, squash, or push", text)

    def test_generated_prompts_do_not_contain_path_escape_control_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo,
                           check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            for prompt in (repo / ".spoon" / "current" / "prompts").glob("*.md"):
                text = prompt.read_text(encoding="utf-8")
                self.assertNotIn("\b", text, prompt.name)
                self.assertNotIn("\t", text, prompt.name)


if __name__ == "__main__":
    unittest.main()
