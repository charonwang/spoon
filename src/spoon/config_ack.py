from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from .io_util import read_bytes, read_json, write_json_atomic
from .paths import ProjectPaths


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ConfigAckStatus:
    needs_confirm: bool
    digest: str
    ack_digest: str | None
    confirmed_at: str | None
    reason: str


def config_digest(paths: ProjectPaths) -> str:
    raw = read_bytes(paths.config) if paths.config.is_file() else b""
    return hashlib.sha256(raw).hexdigest()


def _load_ack(paths: ProjectPaths) -> tuple[str | None, str | None]:
    if not paths.config_ack.is_file():
        return None, None
    raw = read_json(paths.config_ack)
    if not isinstance(raw, dict):
        return None, None
    digest = raw.get("digest")
    confirmed_at = raw.get("confirmed_at")
    return (
        digest if isinstance(digest, str) and digest else None,
        confirmed_at if isinstance(
            confirmed_at, str) and confirmed_at else None,
    )


def config_ack_status(paths: ProjectPaths) -> ConfigAckStatus:
    digest = config_digest(paths)
    ack_digest, confirmed_at = _load_ack(paths)
    if ack_digest is None:
        return ConfigAckStatus(
            needs_confirm=True,
            digest=digest,
            ack_digest=None,
            confirmed_at=None,
            reason="never confirmed (init / first run)",
        )
    if ack_digest != digest:
        return ConfigAckStatus(
            needs_confirm=True,
            digest=digest,
            ack_digest=ack_digest,
            confirmed_at=confirmed_at,
            reason="config.json changed since last confirmation",
        )
    return ConfigAckStatus(
        needs_confirm=False,
        digest=digest,
        ack_digest=ack_digest,
        confirmed_at=confirmed_at,
        reason="matches last confirmation",
    )


def acknowledge_config(paths: ProjectPaths) -> ConfigAckStatus:
    digest = config_digest(paths)
    confirmed_at = _utc_now_iso()
    write_json_atomic(
        paths.config_ack,
        {"digest": digest, "confirmed_at": confirmed_at},
    )
    return ConfigAckStatus(
        needs_confirm=False,
        digest=digest,
        ack_digest=digest,
        confirmed_at=confirmed_at,
        reason="matches last confirmation",
    )


def format_confirmation_line(status: ConfigAckStatus) -> str:
    if status.needs_confirm:
        return f"Confirmation: needed ({status.reason})"
    when = status.confirmed_at or "unknown"
    return f"Confirmation: ok ({status.reason}; ack {when})"
