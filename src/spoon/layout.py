from __future__ import annotations

from .paths import ProjectPaths

LAYOUT_MISSING_MESSAGE = (
    "Spoon layout is missing (need .spoon/current/brief.md). "
    "Run: spoon init"
)


def layout_ready(paths: ProjectPaths) -> bool:
    return paths.current.is_dir() and paths.brief.is_file()
