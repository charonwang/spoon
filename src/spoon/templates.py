from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .constants import (
    BOARD_HEADING_ACCEPTED,
    BOARD_HEADING_PARKED,
    BOARD_HEADING_REJECTED,
    GENERATED_END,
    GENERATED_START,
)


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

{BOARD_HEADING_ACCEPTED}

{BOARD_HEADING_PARKED}

{BOARD_HEADING_REJECTED}

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
plan.md holds only the final, implementation-ready state. Keep review trails out of it: no finding IDs (S1/T2/N3), no "relative to v2" or "as confirmed" notes. Record decisions and rationale in review-board.md.
Use snapshots under .spoon/current/snapshots/ for mechanical context.
Snapshot diffs include checkpoint commits since implementation-base.txt when present, plus unstaged, staged, and untracked sections; use status.txt to cross-check file state.
Do not rely on ~/.cursor/plans after the plan has been adopted.
Markdown file links in plans should use file:///C:/path/to/your/repo/internal/file.go#L82. Do not use C:\\path\\to\\bad.go:82 or bare C:/path/to/bad.go:82 links.
"""


CURSOR_PLAN_BODY = """
Create or revise the plan using brief.md as input. Do not implement code.
When applying review feedback, edit plan.md to the settled final wording; do not leave finding IDs or a change log in it.
"""

CURSOR_IMPLEMENT_BODY = """
Read handoff.md and plan.md. Implement only Approved Changes.
plan.md is the single source of truth; do not redesign it and do not rely on planning chat history.
After completing an approved item, only check existing checkbox items in plan.md that directly match the completed work. Do not add checklist items, rewrite plan text, or record review history in plan.md.
If no existing checkbox maps to completed work, report that gap instead of editing plan.md.
If you hit a real defect or a conflict with the current code, stop and report it instead of changing the approach mid-implementation.
Run the relevant verification listed for the completed approved item or review-fix batch, or explain why it cannot run. After that verification passes, you may create a local checkpoint commit for that batch. Use commit-message.md if helpful. Stage only files for that batch. Do not rewrite history, squash, or push.
"""

PLAN_REVIEW_BODY = """
Review plan.md. Output Verdict, Blocking, Should Fix, Optional, Test Gaps, Questions.
Tag every finding with a severity. If there are no Blocking or Should Fix items, state explicitly: "No blockers, ready for implementation."
Reference plan locations by file link/anchor; do not ask to embed finding IDs into plan.md.
Do not only read the plan; spot-check the current-code assumptions it depends on.
"""

CODE_REVIEW_BODY = """
Review checkpoint commits since implementation-base.txt plus unstaged, staged, and untracked code changes using snapshots/status.txt, snapshots/diff-stat.txt, snapshots/diff.patch, and snapshots/test-output.txt. Output Findings with Severity P1/P2/P3.
"""

FINAL_PLAN_REVIEW_BODY = """
Act as an independent reviewer of .spoon/current/plan.md.

Focus:
- Output only P1/P2/P3 findings.
- If there are no P1/P2, state explicitly: "No blockers, ready for implementation."
- Do not only read the plan; spot-check the current-code assumptions it depends on.
- Verify every past P1/P2 has a matching verification item.
- Check that Markdown file links resolve in the Cursor Plan UI.
- Reference locations by anchor; keep finding IDs and decision history in review-board.md, not in plan.md.
- Do not edit code.
"""

FINAL_CHECK_BODY = """
Use snapshots/status.txt, snapshots/diff-stat.txt, snapshots/diff.patch, snapshots/test-output.txt, snapshots/dependency-check.txt, and snapshots/sensitive-scan.txt. Check checkpoint commits since implementation-base.txt, unstaged, staged, and untracked files, secrets, lockfile consistency, tests, and residual risk.
"""

COMMIT_MESSAGE_BODY = """
Generate a commit message for the current checkpoint batch or final task from snapshots/diff-stat.txt, snapshots/diff.patch, snapshots/test-output.txt, and Accepted For Handoff. For a checkpoint batch, describe only the staged files and the matching approved item or review fix. Do not imply the whole task is complete unless this is the final commit. Do not rely on chat memory.
"""


def prompt_templates() -> dict[str, str]:
    return {
        "cursor-plan.md": COMMON_PROMPT_HEADER + CURSOR_PLAN_BODY,
        "cursor-implement.md": COMMON_PROMPT_HEADER + CURSOR_IMPLEMENT_BODY,
        "codex-plan-review.md": COMMON_PROMPT_HEADER + PLAN_REVIEW_BODY,
        "claude-plan-review.md": COMMON_PROMPT_HEADER + PLAN_REVIEW_BODY,
        "codex-code-review.md": COMMON_PROMPT_HEADER + CODE_REVIEW_BODY,
        "claude-code-review.md": COMMON_PROMPT_HEADER + CODE_REVIEW_BODY,
        "final-plan-review.md": COMMON_PROMPT_HEADER + FINAL_PLAN_REVIEW_BODY,
        "final-check.md": COMMON_PROMPT_HEADER + FINAL_CHECK_BODY,
        "commit-message.md": COMMON_PROMPT_HEADER + COMMIT_MESSAGE_BODY,
    }
