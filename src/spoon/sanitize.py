from __future__ import annotations

import re
from typing import Any

# Common credential / token shapes. Intentionally conservative replacements so
# snapshots and event logs do not persist raw secrets when commands leak them.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|"
            r"passwd|client[_-]?secret)\b(\s*[:=]\s*)([^\s\"']+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)(\S+)"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"\bsk-(?:ant|proj|svcacct)?-[A-Za-z0-9_-]{16,}\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY_ID]",
    ),
    (
        re.compile(
            r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----[\s\S]*?"
            r"-----END (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
)


def redact_secrets(text: str) -> str:
    """Replace common secret patterns in ``text`` with redaction markers."""
    if not text:
        return text
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_secrets_in_data(value: Any) -> Any:
    """Recursively redact secrets inside JSON-compatible structures."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_secrets_in_data(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_secrets_in_data(item) for key, item in value.items()}
    return value


def scan_for_secrets(text: str) -> list[str]:
    """Return human-readable labels for secret patterns found in ``text``."""
    if not text:
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for pattern, replacement in _SECRET_PATTERNS:
        if pattern.search(text):
            label = replacement if replacement.startswith(
                "[") else "[REDACTED]"
            if label not in seen:
                seen.add(label)
                labels.append(label)
    return labels
