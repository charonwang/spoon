from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from ..constants import (
    BOARD_HEADING_ACCEPTED,
    BOARD_HEADING_PARKED,
    BOARD_HEADING_REJECTED,
    GENERATED_START,
)
from ..io_util import read_text, write_text
from ..paths import find_repo_root, project_paths
from ..templates import review_board_template


def register(subparsers):
    parser = subparsers.add_parser("handoff", help="Generate handoff from accepted decisions.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def extract_accepted_for_handoff(board_text: str) -> str:
    match = re.search(rf"(?m)^{re.escape(BOARD_HEADING_ACCEPTED)}\s*$", board_text)
    if match is None:
        return ""

    remainder = board_text[match.end() :]
    stop = re.search(
        rf"(?m)^(?:{re.escape(BOARD_HEADING_PARKED)}\s*$"
        rf"|{re.escape(BOARD_HEADING_REJECTED)}\s*$"
        rf"|{re.escape(GENERATED_START)})",
        remainder,
    )
    accepted = remainder[: stop.start() if stop else len(remainder)]
    return accepted.strip()


def generate_handoff(repo: Path) -> None:
    paths = project_paths(repo)
    if not paths.review_board.exists():
        write_text(paths.review_board, review_board_template())

    board_text = read_text(paths.review_board)
    accepted = extract_accepted_for_handoff(board_text)
    body = accepted if accepted else "_No approved changes yet._"
    write_text(
        paths.handoff,
        (
            "# Agent Handoff\n\n"
            "## Read First\n\n"
            "- .spoon/current/plan.md\n"
            "- .spoon/current/review-board.md\n\n"
            "## Approved Changes\n\n"
            "Only implement the items below.\n\n"
            f"{body}\n\n"
            "## Constraints\n\n"
            "- plan.md is the single source of truth; do not redesign it and do not rely on planning chat history.\n"
            "- After completing an approved item, only check existing checkbox items in plan.md "
            "that directly match the completed work.\n"
            "- Do not add checklist items, rewrite plan text, or record review history in plan.md.\n"
            "- If no existing checkbox maps to completed work, report that gap instead of editing plan.md.\n"
            "- Keep changes scoped to Approved Changes.\n"
            "- Do not implement Optional or Parked findings.\n"
            "- On a defect or conflict with the code, stop and report instead of changing the approach.\n"
            "- Preserve unrelated user changes.\n"
            "- Run the relevant verification for the completed approved item or review-fix batch, "
            "or explain why it cannot run.\n"
            "- After relevant verification passes, you may create a local checkpoint commit for that batch.\n"
            "- Stage only files for that batch. Do not rewrite history, squash, or push.\n"
            "- After implementation, summarize changed files, verification output, and remaining risk.\n"
        ),
    )


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    generate_handoff(repo)
    print(f"Handoff written to {project_paths(repo).handoff}")
    return 0
