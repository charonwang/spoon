from __future__ import annotations

import re

GROUPS = ["Blocking", "Should Fix", "Optional", "Test Gaps", "Needs Triage"]
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")

HEADING_GROUPS = {
    "blocking": "Blocking",
    "should fix": "Should Fix",
    "optional": "Optional",
    "test gaps": "Test Gaps",
    "needs triage": "Needs Triage",
    "questions": "Needs Triage",
    "residual risk": "Optional",
}


def empty_groups() -> dict[str, list[str]]:
    return {name: [] for name in GROUPS}


def heading_label(raw_line: str) -> str | None:
    match = HEADING_RE.match(raw_line)
    if match is None:
        return None
    return match.group(2).strip().rstrip(":").casefold()


def explicit_group(text: str) -> str | None:
    if re.search(r"\[CONFLICT\]", text, re.IGNORECASE):
        return "Needs Triage"
    if re.search(r"\[BLOCKING\]|(?:^|\n)\s*(?:Severity:\s*P1\b|P1\s*:)", text, re.IGNORECASE):
        return "Blocking"
    if re.search(r"\[SUGGEST\]|(?:^|\n)\s*(?:Severity:\s*P2\b|P2\s*:)", text, re.IGNORECASE):
        return "Should Fix"
    if re.search(r"(?:^|\n)\s*(?:Severity:\s*P3\b|P3\s*:)", text, re.IGNORECASE):
        return "Optional"
    if re.search(r"\[TESTGAP\]", text, re.IGNORECASE):
        return "Test Gaps"
    return None


def classify_review_text(source: str, text: str) -> dict[str, list[str]]:
    groups = empty_groups()
    current: str | None = None
    ignore_prose = False
    block: list[str] = []
    unparsed: list[str] = []

    def flush() -> None:
        nonlocal block
        if not block:
            return
        body = "\n  ".join(block)
        group = explicit_group(body) or current
        if group is None:
            groups["Needs Triage"].append(f"[{source}] [PARSER WARNING] {body}")
        else:
            groups[group].append(f"[{source}] {body}")
        block = []

    def flush_unparsed() -> None:
        nonlocal unparsed
        if not unparsed:
            return
        groups["Needs Triage"].append(
            f"[{source}] [PARSER WARNING] Unparsed content: " + " | ".join(unparsed)
        )
        unparsed = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = HEADING_RE.match(raw_line)
        if heading_match is not None:
            heading_text = heading_match.group(2).strip()
            heading_key = heading_text.rstrip(":").casefold()
            if heading_key in HEADING_GROUPS or heading_key in {"verdict", "summary"}:
                flush()
                flush_unparsed()
                current = HEADING_GROUPS.get(heading_key)
                ignore_prose = heading_key in {"verdict", "summary"}
                continue
            # An unknown heading such as "### S1: ..." inside an active group is a
            # finding sub-heading: start a finding block from it and let the
            # following prose append, instead of resetting the group context.
            if current is not None and not ignore_prose:
                flush()
                block = [heading_text]
                continue
            # Otherwise treat it as a generic section boundary (matches the
            # original behavior for headings like "## Findings").
            flush()
            flush_unparsed()
            current = None
            ignore_prose = False
            continue
        if raw_line.lstrip().startswith("- "):
            if ignore_prose:
                continue
            flush()
            block = [raw_line.lstrip()[2:].strip()]
            continue
        if block:
            block.append(line)
            continue
        if not ignore_prose and line.casefold().rstrip(" .") not in {
            "pass",
            "changes_requested",
            "changes requested",
            "no blockers, ready for implementation",
        }:
            unparsed.append(line)

    flush()
    flush_unparsed()
    return groups


def merge_groups(items: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    merged = empty_groups()
    for grouped in items:
        for name in GROUPS:
            merged[name].extend(grouped[name])
    return merged


def render_generated_findings(grouped: dict[str, list[str]]) -> str:
    parts = ["## Generated Findings", ""]
    for name in GROUPS:
        parts.append(f"### {name}")
        parts.append("")
        lines = grouped.get(name, [])
        if lines:
            parts.extend(f"- {line}" for line in lines)
            parts.append("")
        else:
            parts.append("_None._")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"
