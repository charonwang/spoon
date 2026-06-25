#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spoon.export_policy import (
    ExportSeverity,
    discover_task_export_dirs,
    scan_export_tree,
)


def validate_task_dir(task_dir: Path) -> tuple[list, int, int]:
    findings = scan_export_tree(task_dir)
    blocking = [item for item in findings if item.severity is ExportSeverity.BLOCKING]
    warnings = [item for item in findings if item.severity is ExportSeverity.WARNING]
    return findings, len(blocking), len(warnings)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a spoon-history export tree against shared export rules.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help=(
            "Task export directory, or a tasks/ root to discover and validate tasks/*/*."
        ),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    task_dirs = discover_task_export_dirs(root)
    if not task_dirs:
        print(f"no task export directories discovered under {root}")
        print("blocking=0 warnings=0")
        return 0

    total_blocking = 0
    total_warnings = 0
    exit_code = 0
    for task_dir in task_dirs:
        print(f"validating {task_dir}")
        findings, blocking_count, warning_count = validate_task_dir(task_dir)
        total_blocking += blocking_count
        total_warnings += warning_count
        for item in findings:
            print(f"{item.severity.value}\t{item.source}\t{item.message}")
        if blocking_count:
            exit_code = 1
    print(f"blocking={total_blocking} warnings={total_warnings}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
