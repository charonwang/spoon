from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .constants import GENERATED_END, GENERATED_START


def brief_template() -> str:
    return """# Brief

## Goal

## Non-Goals

## Constraints

## Current Guess

## Open Questions
"""


def blank_template() -> str:
    return ""


def review_board_template() -> str:
    return f"""# Review Board

## Decisions

### Accepted For Handoff

### Parked

### Rejected

{GENERATED_START}
## Generated Findings

### Blocking

### Should Fix

### Optional

### Test Gaps

### Needs Triage
{GENERATED_END}
"""


def metadata_template(repo: Path, created_at: datetime) -> str:
    data = {
        "repo": str(repo),
        "created_at": created_at.isoformat(timespec="seconds"),
        "last_snapshot_at": None,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


COMMON_PROMPT_HEADER = """Canonical task workspace: .spoon/current/
Canonical plan: .spoon/current/plan.md
Use snapshots under .spoon/current/snapshots/ for mechanical context.
Snapshot diffs include unstaged, staged, and untracked sections; use status.txt to cross-check file state.
Do not rely on ~/.cursor/plans after the plan has been adopted.
Markdown file links in plans should use file:///C:/path/to/your/repo/internal/file.go#L82. Do not use C:\\path\\to\\bad.go:82 or bare C:/path/to/bad.go:82 links.
"""


def prompt_templates() -> dict[str, str]:
    return {
        "cursor-plan.md": COMMON_PROMPT_HEADER
        + "\nCreate or revise the plan using brief.md as input. Do not implement code.\n",
        "cursor-implement.md": COMMON_PROMPT_HEADER
        + "\nRead handoff.md and plan.md. Implement only Approved Changes.\n",
        "codex-plan-review.md": COMMON_PROMPT_HEADER
        + "\nReview plan.md. Output Verdict, Blocking, Should Fix, Optional, Test Gaps, Questions.\n",
        "claude-plan-review.md": COMMON_PROMPT_HEADER
        + "\nReview plan.md. Output Verdict, Blocking, Should Fix, Optional, Test Gaps, Questions.\n",
        "codex-code-review.md": COMMON_PROMPT_HEADER
        + "\nReview unstaged, staged, and untracked code changes using snapshots/status.txt, snapshots/diff-stat.txt, snapshots/diff.patch, and snapshots/test-output.txt. Output Findings with Severity P1/P2/P3.\n",
        "claude-code-review.md": COMMON_PROMPT_HEADER
        + "\nReview unstaged, staged, and untracked code changes using snapshots/status.txt, snapshots/diff-stat.txt, snapshots/diff.patch, and snapshots/test-output.txt. Output Findings with Severity P1/P2/P3.\n",
        "final-plan-review.md": COMMON_PROMPT_HEADER
        + "\n请作为独立 reviewer 审阅 .spoon/current/plan.md。\n\n重点：\n- 只输出 P1/P2/P3 findings。\n- 如果没有 P1/P2，请明确写“零阻塞，可以进入实现”。\n- 不要只读 plan；请抽查 plan 依赖的当前代码前提。\n- 检查曾经出现过的 P1/P2 是否都有对应验证项。\n- 检查 Markdown 文件链接是否能在 Cursor Plan UI 中跳转。\n- 不要改代码。\n",
        "final-check.md": COMMON_PROMPT_HEADER
        + "\nUse snapshots/status.txt, snapshots/diff-stat.txt, snapshots/diff.patch, snapshots/test-output.txt, snapshots/dependency-check.txt, and snapshots/sensitive-scan.txt. Check unstaged, staged, and untracked files, secrets, lockfile consistency, tests, and residual risk.\n",
        "commit-message.md": COMMON_PROMPT_HEADER
        + "\nGenerate a commit message from snapshots/diff-stat.txt, snapshots/diff.patch, snapshots/test-output.txt, and Accepted For Handoff. Do not rely on chat memory.\n",
    }
