from __future__ import annotations

import tempfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path

from ..io_util import read_text, write_text
from ..path_policy import find_bad_plan_links
from ..paths import find_repo_root, project_paths
from .init_cmd import ensure_git_exclude


def register(subparsers):
    parser = subparsers.add_parser("adopt-plan", help="Move a Cursor plan into .spoon/current/plan.md.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.add_argument("--source", type=Path, required=True, help="Cursor plan file to move.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing non-empty plan.md.")
    parser.set_defaults(handler=run)


def adoption_header(source: Path) -> str:
    return (
        "<!-- spoon adopted-plan\n"
        f"Adopted from: {source}\n"
        f"Adopted at: {datetime.now().isoformat(timespec='seconds')}\n"
        "Canonical source: .spoon/current/plan.md\n"
        "-->\n\n"
    )


def _replace_file(source: Path, target: Path) -> None:
    source.replace(target)


def adopt_plan(repo: Path, source: Path, replace: bool) -> None:
    paths = project_paths(repo)
    if not source.exists():
        raise FileNotFoundError(source)
    if source.resolve() == paths.plan.resolve():
        raise ValueError("source must not be the canonical plan path")
    paths.plan.parent.mkdir(parents=True, exist_ok=True)
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    ensure_git_exclude(paths.repo)
    if paths.plan.exists() and read_text(paths.plan).strip() and not replace:
        raise FileExistsError(paths.plan)

    original = read_text(source)
    adopted_text = adoption_header(source) + original
    warnings = find_bad_plan_links(original)
    plan_sources = [
        "# Plan Sources",
        "",
        f"Adopted from: {source}",
        f"Adopted to: {paths.plan}",
    ]
    if warnings:
        plan_sources.extend(["", "Link warnings:"])
        plan_sources.extend(f"- {warning}" for warning in warnings)
    plan_sources_path = paths.snapshots / "plan-sources.txt"
    target_existed = paths.plan.exists()
    original_target = paths.plan.read_bytes() if target_existed else None
    plan_sources_existed = plan_sources_path.exists()
    original_plan_sources = plan_sources_path.read_bytes() if plan_sources_existed else None
    replaced_target = False
    wrote_plan_sources = False
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=paths.plan.parent,
        prefix=".adopt-plan-",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
    try:
        write_text(temp_path, adopted_text)
        _replace_file(temp_path, paths.plan)
        replaced_target = True
        write_text(plan_sources_path, "\n".join(plan_sources) + "\n")
        wrote_plan_sources = True
        source.unlink()
    except Exception:
        temp_path.unlink(missing_ok=True)
        if replaced_target:
            if target_existed and original_target is not None:
                paths.plan.write_bytes(original_target)
            else:
                paths.plan.unlink(missing_ok=True)
        if wrote_plan_sources or plan_sources_path.exists():
            if plan_sources_existed and original_plan_sources is not None:
                plan_sources_path.write_bytes(original_plan_sources)
            else:
                plan_sources_path.unlink(missing_ok=True)
        raise


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    adopt_plan(repo, args.source, args.replace)
    print(f"Adopted plan into {project_paths(repo).plan}")
    return 0
