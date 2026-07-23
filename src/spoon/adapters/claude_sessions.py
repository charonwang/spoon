from __future__ import annotations

import uuid

from ..io_util import read_json, write_json_atomic
from ..paths import ProjectPaths


class ClaudeSessionsCorruptError(Exception):
    """Raised when claude-sessions.json exists but is invalid."""


def load_claude_sessions(paths: ProjectPaths) -> dict[str, str]:
    if not paths.claude_sessions.exists():
        return {}
    raw = read_json(paths.claude_sessions)
    if not isinstance(raw, dict):
        raise ClaudeSessionsCorruptError(
            "claude-sessions.json must be a JSON object")
    mapping: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ClaudeSessionsCorruptError(
                "claude-sessions.json must map strings to strings")
        mapping[key] = value
    return mapping


def save_claude_session(paths: ProjectPaths, run_id: str, session_id: str) -> None:
    mapping = load_claude_sessions(paths)
    mapping[run_id] = session_id
    write_json_atomic(paths.claude_sessions, mapping)


def ensure_claude_session_id(paths: ProjectPaths, run_id: str) -> tuple[str, bool]:
    """Return (session_id, created_new)."""
    mapping = load_claude_sessions(paths)
    existing = mapping.get(run_id)
    if existing:
        return existing, False
    session_id = str(uuid.uuid4())
    save_claude_session(paths, run_id, session_id)
    return session_id, True
