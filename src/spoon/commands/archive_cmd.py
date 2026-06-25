from __future__ import annotations

import shutil
from argparse import Namespace
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..io_util import read_text
from ..paths import find_repo_root, project_paths
from .init_cmd import create_current_layout


def register(subparsers):
    parser = subparsers.add_parser("archive", help="Archive current task and recreate empty current.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.add_argument("--archive-root", type=Path, required=True, help="Archive root directory.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--force", action="store_true", help="Archive even when required files are empty.")
    parser.set_defaults(handler=run)


def validate_archive_ready(repo: Path, force: bool) -> None:
    if force:
        return
    paths = project_paths(repo)
    if not paths.brief.exists() or not read_text(paths.brief).strip():
        raise ValueError("brief.md is empty")
    if not paths.plan.exists() or not read_text(paths.plan).strip():
        raise ValueError("plan.md is empty")
    review_files = list(paths.reviews.glob("*.md"))
    has_review_content = any(read_text(path).strip() for path in review_files)
    if has_review_content and not paths.review_board.exists():
        raise ValueError("review files exist but review-board.md is missing")


def safe_archive_segment(value: str, label: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty archive name without surrounding whitespace")
    if value in {".", ".."}:
        raise ValueError(f"{label} must not be a path traversal segment")
    if PurePosixPath(value).parts != (value,) or PureWindowsPath(value).parts != (value,):
        raise ValueError(f"{label} must be a single archive path segment")
    if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in value):
        raise ValueError(f"{label} contains characters that are unsafe for archive paths")
    return value


def ensure_inside_archive_root(archive_root: Path, dest: Path) -> None:
    root = archive_root.resolve(strict=False)
    resolved_dest = dest.resolve(strict=False)
    if not resolved_dest.is_relative_to(root):
        raise ValueError("archive destination escapes archive root")


def archive_current(repo: Path, archive_root: Path, project: str, task: str, force: bool) -> Path:
    validate_archive_ready(repo, force)
    paths = project_paths(repo)
    safe_project = safe_archive_segment(project, "project")
    safe_task = safe_archive_segment(task, "task")
    dest = archive_root / safe_project / f"{datetime.now().date().isoformat()}-{safe_task}"
    ensure_inside_archive_root(archive_root, dest)
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    moved = False
    try:
        shutil.move(str(paths.current), str(dest))
        moved = True
        create_current_layout(repo)
    except Exception as exc:
        if moved and dest.exists():
            if paths.current.exists():
                raise RuntimeError(
                    f"Archive recreate failed after moving current to {dest}. "
                    f"A partial current directory exists at {paths.current}; recover manually from {dest}."
                ) from exc
            try:
                paths.current.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(paths.current))
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Archive recreate failed after moving current to {dest}, and rollback failed. "
                    f"Recover manually from {dest}."
                ) from rollback_error
        raise
    return dest


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    dest = archive_current(repo, args.archive_root, args.project, args.task, args.force)
    print(f"Archived current task to {dest}")
    return 0
