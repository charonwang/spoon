from __future__ import annotations

import subprocess
from pathlib import Path

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def current_head_or_empty(repo: Path) -> str:
    result = run_git(repo, ["rev-parse", "--verify", "HEAD"])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return EMPTY_TREE_SHA
