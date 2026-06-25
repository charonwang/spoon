from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..export_policy import ExportBuildResult, ExportSeverity, build_github_export
from ..paths import find_repo_root


def register(subparsers):
    parser = subparsers.add_parser(
        "export-github",
        help="Build a redacted GitHub export candidate directory.",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="New output root directory (must not already exist).",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Path-safe project alias slug.",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Path-safe task id slug.",
    )
    parser.set_defaults(handler=run)


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    result: ExportBuildResult = build_github_export(
        repo,
        args.destination.resolve(),
        args.project,
        args.task,
    )
    if not result.ok:
        blocking = [item for item in result.findings if item.severity is ExportSeverity.BLOCKING]
        print(f"export blocked: {len(blocking)} blocking finding(s)", flush=True)
        for item in blocking:
            print(f"  [{item.source}] {item.message}", flush=True)
        return 1
    assert result.output_dir is not None
    print(f"Export written to {result.output_dir}", flush=True)
    warnings = [item for item in result.findings if item.severity is ExportSeverity.WARNING]
    if warnings:
        print(f"Warnings: {len(warnings)} (see export-report.md)", flush=True)
    return 0
