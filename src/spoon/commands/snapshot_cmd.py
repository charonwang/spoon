from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from datetime import datetime
from pathlib import Path, PurePosixPath

from ..constants import SNAPSHOT_FILES
from ..git_util import current_head_or_empty, run_git
from ..io_util import read_bytes, read_text, write_text
from ..paths import find_repo_root, project_paths
from ..runner.state_store import load_implementation
from ..sanitize import redact_secrets, scan_for_secrets

MAX_UNTRACKED_DIFF_BYTES = 200_000


def register(subparsers):
    parser = subparsers.add_parser(
        "snapshot", help="Refresh git and command snapshots.")
    parser.add_argument("--repo", type=Path,
                        default=Path.cwd(), help="Repository path.")
    parser.add_argument("--test-cmd", default=None,
                        help="Optional test command string.")
    parser.add_argument(
        "--dependency-cmd",
        default=None,
        help="Optional dependency check command string.",
    )
    parser.set_defaults(handler=run)


def command_report(label: str, command: str | None, repo: Path) -> str:
    if not command:
        return f"# {label}\n\nNo command configured.\n"

    print(f"  Running {label.lower()}: {command}", flush=True)
    result = subprocess.run(
        command,
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        shell=True,
        check=False,
    )
    return (
        f"# {label}\n\n"
        f"Command: {command}\n"
        f"Exit code: {result.returncode}\n\n"
        f"## stdout\n\n{result.stdout}\n"
        f"## stderr\n\n{result.stderr}\n"
    )


def report_step(message: str) -> None:
    print(f"  {message}", flush=True)


def git_text(repo: Path, args: list[str]) -> str:
    result = run_git(repo, args)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return output
    return (
        f"Command failed: git {' '.join(args)}\n"
        f"Exit code: {result.returncode}\n\n"
        f"{output}"
    )


def render_sections(sections: list[tuple[str, str]]) -> str:
    rendered = []
    for title, text in sections:
        body = text.rstrip() or "_No changes._"
        rendered.append(f"## {title}\n\n{body}\n")
    return "\n".join(rendered)


def implementation_base_sha(paths) -> tuple[str | None, str | None]:
    if paths.implementation.exists():
        try:
            record = load_implementation(paths)
        except (json.JSONDecodeError, ValueError) as exc:
            warning = f"implementation.json was invalid and was skipped: {exc}"
            if paths.implementation_base.exists():
                return read_text(paths.implementation_base).strip() or None, warning
            return None, warning
        if record is not None and record.base_sha:
            return record.base_sha, None
    if paths.implementation_base.exists():
        return read_text(paths.implementation_base).strip() or None, None
    return None, None


def committed_since_base_sections(
    repo: Path,
    base_sha: str | None,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    if not base_sha:
        return [], []
    head = current_head_or_empty(repo)
    if head == base_sha:
        return [], []
    revision_range = f"{base_sha}..HEAD"
    stat_sections = [
        (
            "Committed Since Implementation Base Diff Stat",
            git_text(repo, ["diff", "--stat", revision_range]),
        )
    ]
    diff_sections = [
        (
            "Committed Since Implementation Base",
            git_text(repo, ["diff", revision_range]),
        )
    ]
    return stat_sections, diff_sections


def git_untracked_paths_or_error(repo: Path) -> tuple[list[str], str | None]:
    result = run_git(repo, ["ls-files", "--others",
                     "--exclude-standard", "-z"])
    if result.returncode == 0:
        return [item for item in result.stdout.split("\0") if item], None

    output = (result.stdout + result.stderr).rstrip()
    message = f"git ls-files failed (exit {result.returncode})"
    if output:
        message += f"\n\n{output}"
    return [], message


def repo_file_from_git_path(repo: Path, git_path: str) -> Path:
    return repo.joinpath(*PurePosixPath(git_path).parts)


def render_untracked_stat(paths: list[str], error: str | None) -> str:
    if error:
        return error
    if not paths:
        return ""
    return "\n".join(f"{path} | untracked" for path in paths)


def render_untracked_file_diff(repo: Path, git_path: str) -> str:
    path = repo_file_from_git_path(repo, git_path)
    header = (
        f"diff --git a/{git_path} b/{git_path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{git_path}\n"
    )
    if not path.is_file():
        return header + "# Skipped: not a regular file.\n"

    data = read_bytes(path)
    if len(data) > MAX_UNTRACKED_DIFF_BYTES:
        return (
            header
            + f"# Skipped: file is {len(data)} bytes, above the "
            + f"{MAX_UNTRACKED_DIFF_BYTES} byte snapshot limit.\n"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return header + "# Skipped: binary or non-UTF-8 file.\n"

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized == "":
        return header + "@@\n"
    body = "\n".join(f"+{line}" for line in normalized.splitlines())
    return header + "@@\n" + body + "\n"


def render_untracked_diff(repo: Path, paths: list[str], error: str | None) -> str:
    if error:
        return error
    if not paths:
        return ""
    return "\n".join(render_untracked_file_diff(repo, path).rstrip() for path in paths) + "\n"


def update_metadata_snapshot_time(metadata_path: Path, repo: Path) -> None:
    if not metadata_path.exists():
        return

    snapshot_time = datetime.now().isoformat(timespec="seconds")
    try:
        data = json.loads(read_text(metadata_path))
        if not isinstance(data, dict):
            raise ValueError("metadata.json root is not an object")
    except (json.JSONDecodeError, ValueError):
        data = {
            "repo": str(repo),
            "created_at": snapshot_time,
            "last_snapshot_at": None,
            "metadata_warning": "metadata.json was invalid and was rebuilt by spoon snapshot.",
        }

    data["last_snapshot_at"] = snapshot_time
    write_text(metadata_path, json.dumps(
        data, ensure_ascii=False, indent=2) + "\n")


def render_sensitive_scan(snapshot_texts: list[str]) -> str:
    findings: list[str] = []
    for text in snapshot_texts:
        for label in scan_for_secrets(text):
            findings.append(f"- matched pattern family {label}")
    # De-dupe while preserving order.
    unique: list[str] = []
    seen: set[str] = set()
    for item in findings:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    if not unique:
        return (
            "# Sensitive Scan\n\n"
            "Status: passed\n\n"
            "No common secret patterns detected in snapshot command output "
            "or collected diffs (heuristic scan).\n"
        )
    body = "\n".join(unique)
    return (
        "# Sensitive Scan\n\n"
        "Status: failed\n\n"
        "Common secret patterns were detected and redacted in snapshot "
        "artifacts before write:\n\n"
        f"{body}\n"
    )


def snapshot_file(paths, name: str) -> Path:
    if name not in SNAPSHOT_FILES:
        raise ValueError(f"unknown snapshot file: {name}")
    return paths.snapshots / name


def create_snapshot(repo: Path, test_cmd: str | None, dependency_cmd: str | None) -> None:
    paths = project_paths(repo)
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    report_step("Collecting git status and diffs...")
    untracked_paths, untracked_error = git_untracked_paths_or_error(repo)
    base_sha, base_warning = implementation_base_sha(paths)
    committed_stat_sections, committed_diff_sections = committed_since_base_sections(
        repo,
        base_sha,
    )
    if base_warning:
        committed_stat_sections.insert(
            0, ("Implementation Base Warning", base_warning))
        committed_diff_sections.insert(
            0, ("Implementation Base Warning", base_warning))

    status_text = git_text(repo, ["status", "--short"])
    diff_stat_text = render_sections(
        committed_stat_sections
        + [
            ("Unstaged Diff Stat", git_text(repo, ["diff", "--stat"])),
            ("Staged Diff Stat", git_text(
                repo, ["diff", "--cached", "--stat"])),
            ("Untracked Files", render_untracked_stat(
                untracked_paths, untracked_error)),
        ],
    )
    diff_patch_text = render_sections(
        committed_diff_sections
        + [
            ("Unstaged Diff", git_text(repo, ["diff"])),
            ("Staged Diff", git_text(repo, ["diff", "--cached"])),
            ("Untracked Files", render_untracked_diff(
                repo, untracked_paths, untracked_error)),
        ],
    )
    recent_commits_text = git_text(repo, ["log", "--oneline", "-n", "10"])
    test_output_text = command_report("Test Output", test_cmd, repo)
    dependency_text = command_report("Dependency Check", dependency_cmd, repo)
    sensitive_scan_text = render_sensitive_scan(
        [
            status_text,
            diff_stat_text,
            diff_patch_text,
            recent_commits_text,
            test_output_text,
            dependency_text,
        ]
    )

    write_text(snapshot_file(paths, "status.txt"), redact_secrets(status_text))
    write_text(snapshot_file(paths, "diff-stat.txt"),
               redact_secrets(diff_stat_text))
    write_text(snapshot_file(paths, "diff.patch"),
               redact_secrets(diff_patch_text))
    write_text(
        snapshot_file(paths, "recent-commits.txt"),
        redact_secrets(recent_commits_text),
    )
    write_text(snapshot_file(paths, "test-output.txt"),
               redact_secrets(test_output_text))
    write_text(
        snapshot_file(paths, "dependency-check.txt"),
        redact_secrets(dependency_text),
    )
    sensitive_path = snapshot_file(paths, "sensitive-scan.txt")
    if not (sensitive_path.exists() and read_text(sensitive_path).strip()):
        write_text(sensitive_path, sensitive_scan_text)
    update_metadata_snapshot_time(paths.metadata, repo)
    report_step("Done.")


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    create_snapshot(repo, args.test_cmd, args.dependency_cmd)
    print(f"Snapshot written to {project_paths(repo).snapshots}")
    return 0
