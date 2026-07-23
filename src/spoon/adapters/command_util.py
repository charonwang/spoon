from __future__ import annotations

import shutil
from pathlib import Path


def find_executable(command: str) -> str | None:
    """Return an absolute/PATH-resolved executable path, or None if missing."""
    candidate = Path(command)
    if candidate.is_file():
        return str(candidate.resolve())
    return shutil.which(command)


def resolve_executable(command: str) -> str:
    """Resolve a CLI name to a path CreateProcess can launch on Windows.

    Bare names like ``codex`` often resolve to ``codex.cmd`` via PATH. Passing
    only the bare name to ``subprocess`` without a shell fails with
    FileNotFoundError; ``shutil.which`` + the full path works.
    """
    found = find_executable(command)
    if found:
        return found
    return command
