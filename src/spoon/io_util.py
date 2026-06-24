from __future__ import annotations

from pathlib import Path


def _normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_normalize_lf(text))


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return _normalize_lf(handle.read())


def append_unique_line(path: Path, line: str) -> None:
    candidate = _normalize_lf(line).strip()
    existing = read_text(path) if path.exists() else ""
    lines = [item.strip() for item in existing.splitlines()]
    if candidate in lines:
        return
    suffix = "" if existing == "" or existing.endswith("\n") else "\n"
    write_text(path, existing + suffix + _normalize_lf(line).rstrip() + "\n")


def replace_between_markers(text: str, start: str, end: str, replacement: str) -> str:
    normalized = _normalize_lf(text)
    start_index = normalized.find(start)
    if start_index == -1:
        raise ValueError("start marker not found")
    end_index = normalized.find(end, start_index + len(start))
    if end_index == -1:
        raise ValueError("end marker not found")
    body = _normalize_lf(replacement).rstrip("\n")
    return (
        normalized[: start_index + len(start)]
        + "\n"
        + body
        + "\n"
        + normalized[end_index:]
    )
