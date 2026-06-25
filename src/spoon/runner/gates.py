from __future__ import annotations

import re
from dataclasses import dataclass

from ..commands.board_cmd import generate_board
from ..commands.handoff_cmd import extract_accepted_for_handoff
from ..constants import GENERATED_END, GENERATED_START
from ..io_util import read_text
from ..paths import ProjectPaths

SECTION_RE = re.compile(
    r"(?m)^### (?P<name>Blocking|Should Fix|Optional|Test Gaps|Needs Triage)\s*$"
)


@dataclass(frozen=True)
class GateResult:
    ready: bool
    needs_user: bool
    reason: str


def generated_findings_text(board_text: str) -> str:
    start = board_text.find(GENERATED_START)
    end = board_text.find(GENERATED_END)
    if start == -1 or end == -1 or start >= end:
        generated = board_text.find("## Generated Findings")
        if generated == -1:
            return ""
        return board_text[generated:]
    return board_text[start + len(GENERATED_START) : end]


def section_items(board_text: str, section_name: str) -> list[str]:
    headings = list(SECTION_RE.finditer(board_text))
    for index, heading in enumerate(headings):
        if heading.group("name") != section_name:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(board_text)
        body = board_text[heading.end() : end]
        return [
            line.lstrip()[2:].strip()
            for line in body.splitlines()
            if line.lstrip().startswith("- ") and line.strip() != "- _None._"
        ]
    return []


def _review_ready(paths: ProjectPaths, review_names: tuple[str, ...]) -> GateResult:
    missing = []
    for name in review_names:
        path = paths.reviews / name
        if not path.is_file() or not read_text(path).strip():
            missing.append(name)
    if missing:
        return GateResult(
            ready=False,
            needs_user=False,
            reason=f"Missing reviews: {', '.join(missing)}",
        )
    return GateResult(ready=True, needs_user=False, reason="")


def _board_gate(paths: ProjectPaths) -> GateResult:
    generate_board(paths.repo)
    board_text = read_text(paths.review_board)
    findings = generated_findings_text(board_text)
    blocking = section_items(findings, "Blocking")
    triage = section_items(findings, "Needs Triage")
    if blocking or triage:
        parts = []
        if blocking:
            parts.append(f"Blocking items: {len(blocking)}")
        if triage:
            parts.append(f"Needs Triage items: {len(triage)}")
        return GateResult(
            ready=False,
            needs_user=True,
            reason="; ".join(parts),
        )
    return GateResult(ready=True, needs_user=False, reason="")


PLAN_REVIEWS = ("codex-plan.md", "claude-plan.md", "final-plan-review.md")
CODE_REVIEWS = ("codex-code.md", "claude-code.md", "cursor-self-review.md")


def plan_review_gate(paths: ProjectPaths) -> GateResult:
    review_check = _review_ready(paths, PLAN_REVIEWS)
    if not review_check.ready:
        return review_check
    return _board_gate(paths)


def code_review_gate(paths: ProjectPaths) -> GateResult:
    review_check = _review_ready(paths, CODE_REVIEWS)
    if not review_check.ready:
        return review_check
    return _board_gate(paths)


def implementation_gate(paths: ProjectPaths) -> GateResult:
    if not paths.handoff.is_file() or not read_text(paths.handoff).strip():
        return GateResult(
            ready=False,
            needs_user=True,
            reason="Approved handoff is missing.",
        )
    accepted = extract_accepted_for_handoff(read_text(paths.review_board))
    if not accepted or accepted == "_No approved changes yet._":
        return GateResult(
            ready=False,
            needs_user=True,
            reason="No approved handoff items on the review board.",
        )
    return GateResult(ready=True, needs_user=False, reason="")


def final_check_gate(paths: ProjectPaths) -> GateResult:
    board_result = _board_gate(paths)
    if not board_result.ready:
        return board_result
    findings = generated_findings_text(read_text(paths.review_board))
    should_fix = section_items(findings, "Should Fix")
    if should_fix:
        return GateResult(
            ready=False,
            needs_user=True,
            reason=f"Remaining Should Fix items: {len(should_fix)}",
        )
    return GateResult(ready=True, needs_user=False, reason="")
