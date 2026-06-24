from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..constants import GENERATED_END, GENERATED_START
from ..io_util import read_text, replace_between_markers, write_text
from ..paths import find_repo_root, project_paths
from ..review_parser import classify_review_text, merge_groups, render_generated_findings
from ..templates import review_board_template


def register(subparsers):
    parser = subparsers.add_parser("board", help="Summarize existing review files.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def ensure_generated_markers(board: str) -> str:
    start_index = board.find(GENERATED_START)
    end_index = board.find(GENERATED_END)
    if start_index != -1 and end_index != -1 and start_index < end_index:
        return board

    generated_heading = board.find("## Generated Findings")
    cut_candidates = [
        index for index in (start_index, end_index, generated_heading) if index != -1
    ]
    cleaned = board[: min(cut_candidates)].rstrip() if cut_candidates else board.rstrip()
    prefix = f"{cleaned}\n\n" if cleaned else ""
    return f"{prefix}{GENERATED_START}\n{GENERATED_END}\n"


def generate_board(repo: Path) -> None:
    paths = project_paths(repo)
    if not paths.review_board.exists():
        write_text(paths.review_board, review_board_template())

    grouped_sources = []
    for review_path in sorted(paths.reviews.glob("*.md")):
        text = read_text(review_path)
        if text.strip():
            grouped_sources.append(classify_review_text(review_path.name, text))

    generated = render_generated_findings(merge_groups(grouped_sources))
    board = ensure_generated_markers(read_text(paths.review_board))
    updated = replace_between_markers(board, GENERATED_START, GENERATED_END, generated)
    write_text(paths.review_board, updated)


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    generate_board(repo)
    print(f"Review board written to {project_paths(repo).review_board}")
    return 0
