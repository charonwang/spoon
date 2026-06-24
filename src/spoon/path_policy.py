from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import unquote

PATH_TOKEN_RE = re.compile(
    r"file:///[A-Za-z]:/[^\s)]+|"
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s)]+|"
    r"\\\\[^\s)]+|"
    r"\\Users\\[^\s)]+",
    re.IGNORECASE,
)
GOOD_FILE_URI_RE = re.compile(r"^file:///[A-Za-z]:/[^\s)]+#L\d+$", re.IGNORECASE)
LINE_SUFFIX_RE = re.compile(r"(?:#L|:)(\d+)$", re.IGNORECASE)
FILE_URI_PREFIX_RE = re.compile(r"^file:///+", re.IGNORECASE)


@dataclass(frozen=True)
class RewriteResult:
    text: str
    warnings: tuple[str, ...]


def iter_local_path_tokens(text: str) -> list[str]:
    return [match.group(0) for match in PATH_TOKEN_RE.finditer(text)]


def find_bad_plan_links(text: str) -> list[str]:
    return [token for token in iter_local_path_tokens(text) if not GOOD_FILE_URI_RE.fullmatch(token)]


def _split_line_suffix(token: str) -> tuple[str, str]:
    match = LINE_SUFFIX_RE.search(token)
    if not match:
        return token, ""
    return token[: match.start()], f"#L{match.group(1)}"


def _to_windows_path(text: str) -> PureWindowsPath:
    return PureWindowsPath(text)


def _relative_windows_path(path: PureWindowsPath, root: PureWindowsPath) -> PureWindowsPath | None:
    path_parts = [part.casefold() for part in path.parts]
    root_parts = [part.casefold() for part in root.parts]
    if len(path_parts) < len(root_parts):
        return None
    if path_parts[: len(root_parts)] != root_parts:
        return None
    remainder = path.parts[len(root.parts) :]
    return PureWindowsPath(*remainder) if remainder else PureWindowsPath(".")


def _normalize_path_token(token: str) -> PureWindowsPath:
    if token.lower().startswith("file:///"):
        stripped = FILE_URI_PREFIX_RE.sub("", token)
        return _to_windows_path(unquote(stripped).replace("/", "\\"))
    return _to_windows_path(token)


def rewrite_local_links_for_export(text: str, repo_root: Path, project_alias: str) -> RewriteResult:
    root = _to_windows_path(str(repo_root))
    warnings: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        base, line_suffix = _split_line_suffix(token)
        candidate = _normalize_path_token(base)
        relative = _relative_windows_path(candidate, root)
        if relative is None:
            replacement = f"<local-path>{line_suffix}"
        else:
            replacement = f"repo://{project_alias}/{relative.as_posix()}{line_suffix}"
        warnings.append(f"rewrote local path: {token} -> {replacement}")
        return replacement

    rewritten = PATH_TOKEN_RE.sub(replace, text)
    return RewriteResult(rewritten, tuple(warnings))
