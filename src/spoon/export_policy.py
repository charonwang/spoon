from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .io_util import read_text, write_json_atomic, write_text
from .path_policy import iter_local_path_tokens, rewrite_local_links_for_export
from .paths import ProjectPaths, project_paths

ALLOWED_EXPORT_FILENAMES = frozenset(
    {
        "brief.md",
        "plan.md",
        "review-board.md",
        "handoff.md",
        "index.json",
        "snapshot-summary.json",
        "export-report.md",
    }
)

MARKDOWN_EXPORT_FILES = frozenset(
    {"brief.md", "plan.md", "review-board.md", "handoff.md"},
)

BLOCKED_EXPORT_FILENAMES = frozenset(
    {
        "diff.patch",
        "status.txt",
        "diff-stat.txt",
        "test-output.txt",
        "dependency-check.txt",
        "sensitive-scan.txt",
    }
)

SNAPSHOT_SUMMARY_KEYS = frozenset(
    {
        "captured_at",
        "changed_file_count",
        "test_status",
        "dependency_check",
        "sensitive_scan",
        "raw_snapshots_exported",
    }
)

STATUS_ENUM = frozenset({"passed", "failed", "not_run", "unknown"})

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

SESSION_ID_RE = re.compile(r"\bsession_id\b", re.IGNORECASE)
THREAD_ID_RE = re.compile(r"\bthread_id\b", re.IGNORECASE)
CONVERSATION_ID_RE = re.compile(r"\bconversation_id\b", re.IGNORECASE)
TRANSCRIPT_RE = re.compile(r"agent[\s_-]*transcript|chat[\s_-]*log", re.IGNORECASE)
FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)

BUSINESS_REVIEW_WARNING = (
    "Business semantics in brief.md require manual review before publication."
)
PLAN_REVIEW_WARNING = (
    "Business semantics in plan.md require manual review before publication."
)


class ExportSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class ExportFinding:
    severity: ExportSeverity
    source: str
    message: str


@dataclass(frozen=True)
class ExportBuildResult:
    ok: bool
    output_dir: Path | None
    findings: tuple[ExportFinding, ...]


def validate_slug(value: str, label: str) -> ExportFinding | None:
    if not value or value in {".", ".."}:
        return ExportFinding(
            ExportSeverity.BLOCKING,
            label,
            f"{label} must be a non-empty path-safe slug",
        )
    if "/" in value or "\\" in value or ".." in value:
        return ExportFinding(
            ExportSeverity.BLOCKING,
            label,
            f"{label} must not contain path separators or traversal",
        )
    if any(ch.isupper() for ch in value):
        return ExportFinding(
            ExportSeverity.BLOCKING,
            label,
            f"{label} must be a lowercase [a-z0-9-] slug (uppercase characters are not allowed)",
        )
    if not SLUG_RE.fullmatch(value):
        return ExportFinding(
            ExportSeverity.BLOCKING,
            label,
            f"{label} must match [a-z0-9-] slug rules",
        )
    return None


def export_task_dir(destination: Path, project_alias: str, task_id: str) -> Path:
    return destination / "tasks" / project_alias / task_id


def _command_status(snapshot_text: str) -> str:
    if "No command configured." in snapshot_text:
        return "not_run"
    match = re.search(r"Exit code:\s*(-?\d+)", snapshot_text)
    if match is None:
        return "unknown"
    return "passed" if match.group(1) == "0" else "failed"


def _sensitive_scan_status(snapshot_text: str) -> str:
    lowered = snapshot_text.lower()
    if "not implemented" in lowered or "manual review" in lowered:
        return "unknown"
    if "passed" in lowered or "no issues" in lowered or "clean" in lowered:
        return "passed"
    if "failed" in lowered or "finding" in lowered or "secret" in lowered:
        return "failed"
    return "unknown"


def _iso_timestamp(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
            return parsed.astimezone().isoformat(timespec="seconds")
        except ValueError:
            pass
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _changed_file_count(status_text: str) -> int:
    count = 0
    for line in status_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("Command failed:"):
            continue
        count += 1
    return count


def build_snapshot_summary(paths: ProjectPaths) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if paths.metadata.is_file():
        try:
            loaded = json.loads(read_text(paths.metadata))
            if isinstance(loaded, dict):
                metadata = loaded
        except json.JSONDecodeError:
            pass

    captured_at = _iso_timestamp(
        metadata.get("last_snapshot_at") if isinstance(metadata.get("last_snapshot_at"), str) else None
    )

    status_text = ""
    if (paths.snapshots / "status.txt").is_file():
        status_text = read_text(paths.snapshots / "status.txt")

    test_text = read_text(paths.snapshots / "test-output.txt") if (
        paths.snapshots / "test-output.txt"
    ).is_file() else ""
    dependency_text = read_text(paths.snapshots / "dependency-check.txt") if (
        paths.snapshots / "dependency-check.txt"
    ).is_file() else ""
    sensitive_text = read_text(paths.snapshots / "sensitive-scan.txt") if (
        paths.snapshots / "sensitive-scan.txt"
    ).is_file() else ""

    return {
        "captured_at": captured_at,
        "changed_file_count": _changed_file_count(status_text),
        "test_status": _command_status(test_text),
        "dependency_check": _command_status(dependency_text),
        "sensitive_scan": _sensitive_scan_status(sensitive_text),
        "raw_snapshots_exported": False,
    }


def validate_snapshot_summary(data: object, source: str) -> list[ExportFinding]:
    findings: list[ExportFinding] = []
    if not isinstance(data, dict):
        return [
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                "snapshot-summary.json must be an object",
            )
        ]
    extra = set(data.keys()) - SNAPSHOT_SUMMARY_KEYS
    missing = SNAPSHOT_SUMMARY_KEYS - set(data.keys())
    if extra:
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                f"snapshot-summary.json has unexpected fields: {sorted(extra)}",
            )
        )
    if missing:
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                f"snapshot-summary.json missing fields: {sorted(missing)}",
            )
        )
    if data.get("raw_snapshots_exported") is not False:
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                "raw_snapshots_exported must be false",
            )
        )
    count = data.get("changed_file_count")
    if not isinstance(count, int) or count < 0:
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                "changed_file_count must be a non-negative integer",
            )
        )
    for key in ("test_status", "dependency_check", "sensitive_scan"):
        value = data.get(key)
        if value is not None and value not in STATUS_ENUM:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    source,
                    f"{key} must be one of {sorted(STATUS_ENUM)}",
                )
            )
    serialized = json.dumps(data, ensure_ascii=False)
    for pattern in (SESSION_ID_RE, THREAD_ID_RE, CONVERSATION_ID_RE):
        if pattern.search(serialized):
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    source,
                    f"snapshot-summary.json contains forbidden id token: {pattern.pattern}",
                )
            )
    if iter_local_path_tokens(serialized):
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                "snapshot-summary.json contains local path tokens",
            )
        )
    return findings


def scan_text_content(text: str, source: str) -> list[ExportFinding]:
    findings: list[ExportFinding] = []
    for pattern, label in (
        (SESSION_ID_RE, "session_id"),
        (THREAD_ID_RE, "thread_id"),
        (CONVERSATION_ID_RE, "conversation_id"),
        (TRANSCRIPT_RE, "agent transcript or chat log"),
    ):
        if pattern.search(text):
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    source,
                    f"forbidden content: {label}",
                )
            )
    for match in FENCE_RE.finditer(text):
        lines = match.group(1).splitlines()
        if len(lines) > 60:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    source,
                    f"fenced code block exceeds 60 lines ({len(lines)} lines)",
                )
            )
    for token in iter_local_path_tokens(text):
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                source,
                f"unresolved local path token remains: {token}",
            )
        )
    for blocked_name in BLOCKED_EXPORT_FILENAMES:
        if blocked_name in text:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    source,
                    f"references blocked snapshot artifact: {blocked_name}",
                )
            )
    return findings


def discover_task_export_dirs(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        return []
    if root.name == "tasks":
        discovered: list[Path] = []
        for project_dir in sorted(root.iterdir()):
            if not project_dir.is_dir():
                continue
            for task_dir in sorted(project_dir.iterdir()):
                if task_dir.is_dir():
                    discovered.append(task_dir)
        return discovered
    return [root]


def scan_export_tree(root: Path) -> list[ExportFinding]:
    findings: list[ExportFinding] = []
    if not root.is_dir():
        return [
            ExportFinding(
                ExportSeverity.BLOCKING,
                str(root),
                "export directory does not exist",
            )
        ]
    for path in sorted(root.rglob("*")):
        if path == root:
            continue
        if path.is_dir():
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    f"{path.relative_to(root).as_posix()}/",
                    "nested directories are not allowed in task export root",
                )
            )
            continue
        if path.parent != root:
            rel = path.relative_to(root).as_posix()
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    rel,
                    "export files must live at task root, not in subdirectories",
                )
            )
            continue
        rel = path.name
        name = path.name
        if name in BLOCKED_EXPORT_FILENAMES:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    rel,
                    f"blocked export filename: {name}",
                )
            )
            continue
        if name not in ALLOWED_EXPORT_FILENAMES:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    rel,
                    f"file not on export allowlist: {name}",
                )
            )
            continue
        if name.endswith(".json"):
            if name == "snapshot-summary.json":
                try:
                    findings.extend(
                        validate_snapshot_summary(json.loads(read_text(path)), rel)
                    )
                except json.JSONDecodeError:
                    findings.append(
                        ExportFinding(
                            ExportSeverity.BLOCKING,
                            rel,
                            "snapshot-summary.json is invalid JSON",
                        )
                    )
            else:
                findings.extend(scan_text_content(read_text(path), rel))
        else:
            findings.extend(scan_text_content(read_text(path), rel))
    return findings


def render_export_report(findings: tuple[ExportFinding, ...]) -> str:
    warnings = [item for item in findings if item.severity == ExportSeverity.WARNING]
    blocking = [item for item in findings if item.severity == ExportSeverity.BLOCKING]
    lines = ["# Export Report", ""]
    lines.append(f"Generated at: {_iso_timestamp()}")
    lines.append("")
    lines.append(f"Blocking findings: {len(blocking)}")
    lines.append(f"Warnings: {len(warnings)}")
    lines.append("")
    if blocking:
        lines.append("## Blocking")
        lines.append("")
        for item in blocking:
            lines.append(f"- `{item.source}`: {item.message}")
        lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for item in warnings:
            lines.append(f"- `{item.source}`: {item.message}")
        lines.append("")
    if not blocking and not warnings:
        lines.append("No findings.")
        lines.append("")
    return "\n".join(lines)


def _rewrite_markdown(text: str, repo_root: Path, project_alias: str, source: str) -> tuple[str, list[ExportFinding]]:
    result = rewrite_local_links_for_export(text, repo_root, project_alias)
    findings: list[ExportFinding] = []
    if result.warnings:
        findings.append(
            ExportFinding(
                ExportSeverity.WARNING,
                source,
                f"rewrote {len(result.warnings)} local path token(s)",
            )
        )
    return result.text, findings


def build_github_export(
    repo: Path,
    destination: Path,
    project_alias: str,
    task_id: str,
) -> ExportBuildResult:
    findings: list[ExportFinding] = []
    for label, value in (("project", project_alias), ("task", task_id)):
        slug_issue = validate_slug(value, label)
        if slug_issue is not None:
            findings.append(slug_issue)
    if destination.exists():
        findings.append(
            ExportFinding(
                ExportSeverity.BLOCKING,
                str(destination),
                "destination already exists",
            )
        )
    if any(item.severity == ExportSeverity.BLOCKING for item in findings):
        return ExportBuildResult(False, None, tuple(findings))

    paths = project_paths(repo)
    task_dir = export_task_dir(destination, project_alias, task_id)
    staged_root = Path(tempfile.mkdtemp(prefix="spoon-export-"))
    staged_task = staged_root / task_dir.relative_to(destination)
    staged_task.mkdir(parents=True, exist_ok=True)

    try:
        markdown_sources = {
            "brief.md": paths.brief,
            "plan.md": paths.plan,
            "review-board.md": paths.review_board,
            "handoff.md": paths.handoff,
        }
        markdown_outputs: dict[str, str] = {}
        for name, source_path in markdown_sources.items():
            if not source_path.is_file():
                continue
            text = read_text(source_path)
            if not text.strip():
                continue
            rewritten, rewrite_findings = _rewrite_markdown(
                text,
                paths.repo,
                project_alias,
                name,
            )
            findings.extend(rewrite_findings)
            markdown_outputs[name] = rewritten

        if "brief.md" in markdown_outputs:
            findings.append(
                ExportFinding(
                    ExportSeverity.WARNING,
                    "brief.md",
                    BUSINESS_REVIEW_WARNING,
                )
            )
        if "plan.md" in markdown_outputs:
            findings.append(
                ExportFinding(
                    ExportSeverity.WARNING,
                    "plan.md",
                    PLAN_REVIEW_WARNING,
                )
            )

        for name, text in markdown_outputs.items():
            findings.extend(scan_text_content(text, name))

        snapshot_summary = build_snapshot_summary(paths)
        findings.extend(validate_snapshot_summary(snapshot_summary, "snapshot-summary.json"))

        index_payload = {
            "schema_version": 1,
            "project_alias": project_alias,
            "task_id": task_id,
            "exported_at": _iso_timestamp(),
        }
        index_text = json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n"
        findings.extend(scan_text_content(index_text, "index.json"))

        blocking = [item for item in findings if item.severity == ExportSeverity.BLOCKING]
        if blocking:
            return ExportBuildResult(False, None, tuple(findings))

        for name, text in markdown_outputs.items():
            write_text(staged_task / name, text)
        write_json_atomic(staged_task / "snapshot-summary.json", snapshot_summary)
        write_text(staged_task / "index.json", index_text)

        report_findings = tuple(findings)
        write_text(staged_task / "export-report.md", render_export_report(report_findings))
        findings.extend(scan_export_tree(staged_task))
        blocking = [item for item in findings if item.severity == ExportSeverity.BLOCKING]
        if blocking:
            return ExportBuildResult(False, None, tuple(findings))

        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            findings.append(
                ExportFinding(
                    ExportSeverity.BLOCKING,
                    str(destination),
                    "destination already exists",
                )
            )
            return ExportBuildResult(False, None, tuple(findings))
        shutil.move(str(staged_root / "tasks"), str(destination / "tasks"))
        return ExportBuildResult(True, task_dir, tuple(findings))
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)
