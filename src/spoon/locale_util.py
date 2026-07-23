from __future__ import annotations

import re
from pathlib import Path

from .io_util import read_text

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")


def normalize_language_tag(value: str) -> str:
    text = value.strip().replace("_", "-")
    if not text:
        return "en"
    parts = [part for part in text.split("-") if part]
    if not parts:
        return "en"
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def _sample_natural_language_text(*texts: str) -> str:
    chunks: list[str] = []
    for text in texts:
        stripped = text.strip()
        if not stripped:
            continue
        # Skip Markdown chrome so heading words like "## Goal" do not dominate.
        lines = [
            line
            for line in stripped.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if lines:
            chunks.append("\n".join(lines))
    return "\n".join(chunks)


def detect_language_tag_from_text(text: str) -> str | None:
    """Best-effort tag from user-authored prose. Returns None when unclear."""
    sample = _sample_natural_language_text(text)
    if not sample:
        return None
    if _HIRAGANA_KATAKANA_RE.search(sample):
        return "ja"
    if _HANGUL_RE.search(sample):
        return "ko"
    if _CJK_RE.search(sample):
        return "zh"
    # Latin-script tasks default to English when no stronger signal exists.
    letters = sum(1 for char in sample if char.isalpha())
    if letters >= 24:
        return "en"
    return None


def detect_task_language_tag(brief_text: str = "", plan_text: str = "") -> str:
    """Language of the current task request: brief, then plan, else English.

    Mirrors the host AGENTS.md rule: follow the user's request language; when
    unclear, default to English.
    """
    for source in (brief_text, plan_text):
        detected = detect_language_tag_from_text(source)
        if detected:
            return detected
    return "en"


def detect_task_language_tag_from_paths(
    brief_path: Path | None = None,
    plan_path: Path | None = None,
) -> str:
    brief_text = ""
    plan_text = ""
    if brief_path is not None and brief_path.is_file():
        brief_text = read_text(brief_path)
    if plan_path is not None and plan_path.is_file():
        plan_text = read_text(plan_path)
    return detect_task_language_tag(brief_text, plan_text)


def resolve_language_tag(
    configured: str,
    *,
    brief_text: str = "",
    plan_text: str = "",
) -> str:
    """Resolve config ``language`` (``auto`` or an explicit tag)."""
    text = configured.strip()
    if not text or text.lower() == "auto":
        return detect_task_language_tag(brief_text, plan_text)
    return normalize_language_tag(text)


def language_prompt_instruction(language_tag: str) -> str:
    return (
        f"Task language: {language_tag}. "
        "Write all user-facing prose for this task in that language "
        "(plan.md, review verdicts/summaries/finding text, handoff notes, "
        "commit-message drafts, and similar narrative). "
        "This follows the host rule: match the primary language of the user's "
        "current task request (brief.md, else plan.md); default English when "
        "unclear. Keep identifiers, paths, commands, configuration keys, "
        "Spoon structural headings (## Blocking, ## Should Fix, ## Optional, "
        "## Test Gaps, ## Questions), and severity tags ([BLOCKING], [SUGGEST], "
        "Severity: P1/P2/P3) in English unless a project contract says otherwise."
    )
