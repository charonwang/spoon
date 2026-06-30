from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..io_util import read_text
from ..paths import find_repo_root, project_paths
from ..runner.actions import complete_action, fail_action, is_implementation_action, load_actions
from ..runner.model import ImplementationRecord, utc_now_iso


def register(subparsers):
    parser = subparsers.add_parser("action", help="List or complete workflow actions.")
    action_sub = parser.add_subparsers(dest="action_command")

    list_parser = action_sub.add_parser("list", help="List workflow actions.")
    list_parser.add_argument("--repo", type=Path, default=Path.cwd())
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(handler=run_list)

    complete_parser = action_sub.add_parser("complete", help="Complete a workflow action.")
    complete_parser.add_argument("--repo", type=Path, default=Path.cwd())
    complete_parser.add_argument("--id", required=True, dest="action_id")
    complete_parser.add_argument("--output", type=Path, required=True)
    complete_parser.set_defaults(handler=run_complete)

    fail_parser = action_sub.add_parser("fail", help="Fail a workflow action.")
    fail_parser.add_argument("--repo", type=Path, default=Path.cwd())
    fail_parser.add_argument("--id", required=True, dest="action_id")
    fail_parser.add_argument("--message", required=True)
    fail_parser.set_defaults(handler=run_fail)


def _resolve_output(repo: Path, output: Path) -> Path:
    candidate = output if output.is_absolute() else repo / output
    resolved = candidate.resolve()
    repo_root = repo.resolve()
    if repo_root not in resolved.parents and resolved != repo_root:
        raise ValueError("output path must stay inside the repository")
    current = (repo_root / ".spoon" / "current").resolve()
    if current not in resolved.parents and resolved != current:
        raise ValueError("output path must stay inside .spoon/current/")
    return resolved


def run_list(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    actions = load_actions(paths) if paths.actions.exists() else []
    payload = [action.to_dict() for action in actions]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for action in actions:
            print(f"{action.id}\t{action.kind.value}\t{action.status.value}")
    return 0


def run_complete(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    try:
        output = _resolve_output(repo, args.output)
        actions = load_actions(paths) if paths.actions.exists() else []
        target = next((item for item in actions if item.id == args.action_id), None)
        if target is None:
            raise ValueError(f"unknown action id: {args.action_id}")

        implementation_record: ImplementationRecord | None = None
        if is_implementation_action(target):
            base_sha = target.payload.get("implementation_base_sha")
            if not isinstance(base_sha, str) and paths.implementation_base.exists():
                base_sha = read_text(paths.implementation_base).strip() or None
            implementation_record = ImplementationRecord(
                schema_version=1,
                status="reported_complete",
                action_id=target.id,
                completed_at=utc_now_iso(),
                summary_path=target.output_path or "",
                base_sha=base_sha if isinstance(base_sha, str) else None,
            )
        completed = complete_action(
            paths,
            args.action_id,
            output,
            implementation_record=implementation_record,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), flush=True)
        return 2

    print(f"Completed action {completed.id}")
    return 0


def run_fail(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    try:
        failed = fail_action(paths, args.action_id, args.message)
    except ValueError as exc:
        print(str(exc), flush=True)
        return 2
    print(f"Failed action {failed.id}")
    return 0


def run(args: Namespace) -> int:
    handler = getattr(args, "handler", None)
    if handler is None:
        return 2
    return int(handler(args))
