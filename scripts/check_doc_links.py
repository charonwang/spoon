#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    files = [ROOT / "README.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    for extra in ("skills", "github"):
        root = ROOT / extra
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def resolve_link(source: Path, target: str) -> Path | None:
    target = target.split("#", 1)[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    if target.startswith("/"):
        return ROOT / target.lstrip("/")
    return (source.parent / target).resolve()


def main() -> int:
    errors: list[str] = []
    checked = markdown_files()
    for md in checked:
        text = md.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            href = match.group(1)
            resolved = resolve_link(md, href)
            if resolved is None:
                continue
            if not resolved.is_file():
                rel = md.relative_to(ROOT)
                errors.append(f"{rel}: broken link {href!r}")
    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1
    print(f"checked doc links OK ({len(checked)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
