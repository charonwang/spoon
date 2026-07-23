from __future__ import annotations

from argparse import Namespace
from datetime import datetime
from pathlib import Path

from ..constants import PROMPT_FILES, REVIEW_FILES, SNAPSHOT_FILES
from ..git_util import run_git
from ..io_util import append_unique_line, write_json_atomic, write_text
from ..paths import find_repo_root, project_paths
from ..templates import (
    blank_template,
    brief_template,
    metadata_template,
    review_board_template,
)


def register(subparsers):
    parser = subparsers.add_parser(
        "init", help="Create .spoon/current structure.")
    parser.add_argument("--repo", type=Path,
                        default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def write_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        write_text(path, text)


def git_exclude_path(repo: Path) -> Path:
    result = run_git(repo, ["rev-parse", "--git-path", "info/exclude"])
    if result.returncode == 0 and result.stdout.strip():
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else repo / path
    return repo / ".git" / "info" / "exclude"


def ensure_git_exclude(repo: Path) -> None:
    append_unique_line(git_exclude_path(repo), ".spoon/")


def create_current_layout(repo: Path) -> None:
    paths = project_paths(repo)
    paths.prompts.mkdir(parents=True, exist_ok=True)
    paths.reviews.mkdir(parents=True, exist_ok=True)
    paths.snapshots.mkdir(parents=True, exist_ok=True)

    write_if_missing(paths.brief, brief_template())
    write_if_missing(paths.plan, blank_template())
    write_if_missing(paths.review_board, review_board_template())
    write_if_missing(paths.handoff, blank_template())
    write_if_missing(paths.metadata, metadata_template(
        paths.repo, datetime.now()))

    for name in PROMPT_FILES:
        write_if_missing(paths.prompts / name, blank_template())
    for name in REVIEW_FILES:
        write_if_missing(paths.reviews / name, blank_template())
    for name in SNAPSHOT_FILES:
        write_if_missing(paths.snapshots / name, blank_template())

    if not paths.config.exists():
        write_json_atomic(
            paths.config,
            {
                "experimental_cursor_ui": False,
                "visible_terminals": False,
                "language": "auto",
                "terminal": {
                    "launcher": "windows_terminal",
                    "executable": None,
                    "args": None,
                },
                "agents": {
                    "claude": {
                        "cli": True,
                        "model": None,
                        "ui": "interactive",
                    },
                    "codex": {
                        "cli": False,
                        "desktop": False,
                        "model": None,
                        "reasoning_effort": None,
                        "service_tier": None,
                        "project_map": {},
                    },
                },
            },
        )

    ensure_git_exclude(paths.repo)


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    create_current_layout(repo)
    print(f"Initialized {project_paths(repo).current}")
    print("Config: edit .spoon/config.json — spoon config show / spoon config keys")
    return 0
