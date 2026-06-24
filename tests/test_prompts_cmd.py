import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout
from spoon.commands.prompts_cmd import generate_prompts


class PromptCommandTests(unittest.TestCase):
    def test_generate_prompts_writes_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "final-plan-review.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("Canonical task workspace: .spoon/current/", text)
            self.assertIn(
                "file:///C:/path/to/your/repo/internal/file.go#L82",
                text,
            )
            self.assertIn("零阻塞，可以进入实现", text)

    def test_generate_final_check_prompt_uses_snapshot_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "final-check.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("snapshots/dependency-check.txt", text)
            self.assertIn("snapshots/sensitive-scan.txt", text)
            self.assertIn("unstaged, staged, and untracked", text)

    def test_code_review_prompt_mentions_untracked_diff_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "codex-code-review.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("unstaged, staged, and untracked", text)
            self.assertIn("status.txt", text)

    def test_commit_message_prompt_mentions_real_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            create_current_layout(repo)

            generate_prompts(repo)

            prompt = repo / ".spoon" / "current" / "prompts" / "commit-message.md"
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("snapshots/diff-stat.txt", text)
            self.assertIn("Do not rely on chat memory", text)


if __name__ == "__main__":
    unittest.main()
