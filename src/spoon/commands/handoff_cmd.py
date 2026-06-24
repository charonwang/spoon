from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import re

from ..constants import GENERATED_START
from ..io_util import read_text, write_text
from ..paths import find_repo_root, project_paths
from ..templates import review_board_template


def register(subparsers):
    parser = subparsers.add_parser("handoff", help="Generate handoff from accepted decisions.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def extract_accepted_for_handoff(board_text: str) -> str:
    match = re.search(r"(?m)^### Accepted For Handoff\s*$", board_text)
    if match is None:
        return ""

    remainder = board_text[match.end() :]
    stop = re.search(
        rf"(?m)^(?:### Parked\s*$|### Rejected\s*$|{re.escape(GENERATED_START)})",
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
            "- Keep changes scoped to Approved Changes.\n"
            "- Do not implement Optional or Parked findings.\n"
            "- Preserve unrelated user changes.\n"
            "- Run the listed verification commands or explain why they cannot run.\n"
            "- After implementation, summarize changed files, verification output, and remaining risk.\n"
        ),
    )


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    generate_handoff(repo)
    print(f"Handoff written to {project_paths(repo).handoff}")
    return 0
