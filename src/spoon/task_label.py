from __future__ import annotations

import re

from .io_util import read_text
from .paths import ProjectPaths

_MAX_LABEL_LEN = 24
_SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_MARKDOWN_JUNK_RE = re.compile(r"[#*_`\[\]]+")
_WS_RE = re.compile(r"\s+")


def sanitize_task_label(raw: str) -> str:
    text = _MARKDOWN_JUNK_RE.sub("", raw)
    text = _WS_RE.sub(" ", text).strip(" -–—:|")
    if not text:
        return "current"
    # Prefer the short product name before a title-style colon.
    for sep in ("：", ":"):
        if sep in text:
            head = text.split(sep, 1)[0].strip(" -–—")
            if head:
                text = head
            break
    if len(text) > _MAX_LABEL_LEN:
        text = text[:_MAX_LABEL_LEN].rstrip(" -–—")
    return text or "current"


def extract_task_label_from_brief(brief_text: str) -> str | None:
    matches = list(_SECTION_RE.finditer(brief_text))
    for index, match in enumerate(matches):
        if match.group(1).strip().lower() != "goal":
            continue
        start = match.end()
        end = matches[index + 1].start() if index + \
            1 < len(matches) else len(brief_text)
        body = brief_text[start:end]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("<!--"):
                continue
            return sanitize_task_label(stripped)
    return None


def resolve_task_label(
    paths: ProjectPaths,
    *,
    override: str | None = None,
    existing: str | None = None,
) -> str:
    if override and override.strip():
        return sanitize_task_label(override)
    # Prefer brief Goal over a stale long label persisted mid-run.
    if paths.brief.is_file():
        from_brief = extract_task_label_from_brief(read_text(paths.brief))
        if from_brief:
            return from_brief
    if existing and existing.strip():
        return sanitize_task_label(existing)
    return "current"


def conversation_title(task_label: str) -> str:
    label = sanitize_task_label(task_label)
    return f"Spoon:{label}"
