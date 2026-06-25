from __future__ import annotations

import json
from typing import Any

from ..io_util import read_text
from ..paths import ProjectPaths
from .model import utc_now_iso


class EventsCorruptError(Exception):
    """Raised when events.jsonl exists but contains invalid records."""


def append_event(paths: ProjectPaths, event_type: str, data: dict[str, Any]) -> None:
    paths.events.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "type": event_type,
        "timestamp": utc_now_iso(),
        "data": data,
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with paths.events.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def load_events(paths: ProjectPaths) -> list[dict[str, Any]]:
    if not paths.events.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(read_text(paths.events).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventsCorruptError(f"events.jsonl line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise EventsCorruptError(
                f"events.jsonl line {line_number} must be an object, got {type(item).__name__}"
            )
        events.append(item)
    return events
