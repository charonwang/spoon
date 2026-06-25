from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


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


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return json.load(handle)


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
