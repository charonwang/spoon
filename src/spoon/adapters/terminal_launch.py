from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..io_util import write_json_atomic
from ..spoon_config import TerminalConfig
from .command_util import find_executable

CREATE_NEW_CONSOLE = 0x00000010

# Launchers that need a brand-new console window on Windows.
_NEW_CONSOLE_LAUNCHERS = frozenset({"conhost", "pwsh"})


@dataclass(frozen=True)
class ResolvedTerminal:
    launcher: str
    argv: list[str] | None
    executable: str | None
    note: str


def resolve_launcher_chain(config: TerminalConfig) -> list[str]:
    """Return launcher preference order starting from configured launcher."""
    if config.launcher == "custom":
        return ["custom"]
    if config.launcher == "inline":
        return ["inline"]
    order = [config.launcher]
    for fallback in ("windows_terminal", "pwsh", "conhost", "inline"):
        if fallback not in order:
            order.append(fallback)
    return order


def _ps_single_quote(value: str) -> str:
    """Quote a string for PowerShell single-quoted literals."""
    return "'" + value.replace("'", "''") + "'"


def _pwsh_command_from_argv(inner_argv: list[str]) -> str:
    if not inner_argv:
        raise ValueError("pwsh launcher requires a non-empty command")
    quoted = " ".join(_ps_single_quote(part) for part in inner_argv)
    return f"& {quoted}"


def build_terminal_argv(
    launcher: str,
    *,
    cwd: Path,
    inner_argv: list[str],
    executable: str | None,
    args: tuple[str, ...] | None,
) -> tuple[list[str] | None, str | None, str]:
    """Build process argv for an external terminal wrapping ``inner_argv``.

    Returns (argv_or_None_for_inline, resolved_executable, note).
    For ``conhost`` / ``pwsh``, caller uses CREATE_NEW_CONSOLE on Windows.
    """
    cwd_s = str(cwd.resolve())
    script_placeholder = " ".join(inner_argv)

    if launcher == "inline":
        return None, None, "inline (stream into spoon process)"

    if launcher == "custom":
        if not executable or not args:
            raise ValueError("custom launcher requires executable and args")
        exe = find_executable(executable) or executable
        rendered = [
            part.format(cwd=cwd_s, script=script_placeholder,
                        job=script_placeholder)
            for part in args
        ]
        return [exe, *rendered], exe, f"custom ({exe})"

    if launcher == "windows_terminal":
        name = executable or "wt"
        exe = find_executable(name)
        if exe is None:
            raise FileNotFoundError(
                f"windows_terminal executable not found: {name}")
        return [exe, "-d", cwd_s, "--", *inner_argv], exe, f"windows_terminal ({exe})"

    if launcher == "pwsh":
        name = executable or "pwsh"
        exe = find_executable(name)
        if exe is None:
            raise FileNotFoundError(f"pwsh executable not found: {name}")
        command = _pwsh_command_from_argv(inner_argv)
        return (
            [
                exe,
                "-NoExit",
                "-NoProfile",
                "-WorkingDirectory",
                cwd_s,
                "-Command",
                command,
            ],
            exe,
            f"pwsh ({exe})",
        )

    if launcher == "tabby":
        name = executable or "tabby"
        exe = find_executable(name)
        if exe is None:
            raise FileNotFoundError(f"tabby executable not found: {name}")
        # Tabby CLI is `run [command...]` (no wt-style `--` separator). A leading
        # `--` becomes command[0] and the tab never starts usefully.
        return [exe, "run", *inner_argv], exe, f"tabby ({exe})"

    if launcher == "conhost":
        return list(inner_argv), inner_argv[0], "conhost (new console)"

    raise ValueError(f"unknown launcher: {launcher}")


def resolve_terminal(
    config: TerminalConfig,
    *,
    cwd: Path,
    inner_argv: list[str] | None = None,
    job_path: Path | None = None,
) -> ResolvedTerminal:
    """Resolve an external terminal.

    Prefer ``inner_argv`` (command to run inside the terminal). Legacy callers
    may pass ``job_path`` for the print/stream-json job runner.
    """
    if inner_argv is None:
        if job_path is None:
            raise ValueError("inner_argv or job_path is required")
        py = sys.executable
        inner_argv = [py, "-m", "spoon.adapters.claude_visible_run",
                      "--job", str(job_path.resolve())]

    last_error = ""
    for launcher in resolve_launcher_chain(config):
        try:
            argv, exe, note = build_terminal_argv(
                launcher,
                cwd=cwd,
                inner_argv=inner_argv,
                executable=config.executable if launcher == config.launcher else None,
                args=config.args if launcher == "custom" else None,
            )
            return ResolvedTerminal(
                launcher=launcher,
                argv=argv,
                executable=exe,
                note=note,
            )
        except (FileNotFoundError, ValueError) as exc:
            last_error = str(exc)
            continue
    return ResolvedTerminal(
        launcher="inline",
        argv=None,
        executable=None,
        note=f"inline fallback ({last_error or 'no external terminal'})",
    )


def write_visible_job(
    job_path: Path,
    *,
    cmd: list[str],
    cwd: Path,
    prompt_path: Path,
    capture_path: Path,
    exit_path: Path,
) -> None:
    write_json_atomic(
        job_path,
        {
            "cmd": cmd,
            "cwd": str(cwd.resolve()),
            "prompt_path": str(prompt_path.resolve()),
            "capture_path": str(capture_path.resolve()),
            "exit_path": str(exit_path.resolve()),
        },
    )


def launch_external_terminal(
    resolved: ResolvedTerminal,
    *,
    cwd: Path,
) -> None:
    if resolved.launcher == "inline" or resolved.argv is None:
        raise ValueError("inline launcher has no external process")
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if resolved.launcher in _NEW_CONSOLE_LAUNCHERS and sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NEW_CONSOLE
        # New console owns stdio; do not force DEVNULL or the window stays blank.
        kwargs.pop("stdin", None)
        kwargs.pop("stdout", None)
        kwargs.pop("stderr", None)
    subprocess.Popen(resolved.argv, **kwargs)  # noqa: S603 — argv from resolver


def wait_for_exit_file(exit_path: Path, *, timeout_seconds: int) -> int:
    from ..io_util import read_text

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if exit_path.is_file():
            text = read_text(exit_path).strip()
            if text:
                try:
                    return int(text.splitlines()[0].strip())
                except ValueError:
                    pass
        time.sleep(0.25)
    raise TimeoutError(
        f"timed out after {timeout_seconds}s waiting for {exit_path}"
    )


def wait_for_nonempty_file(
    path: Path,
    *,
    timeout_seconds: int,
    stable_seconds: float = 1.0,
    poll_seconds: float = 0.5,
) -> str:
    """Wait until ``path`` has non-empty content that is stable for a beat."""
    from ..io_util import read_text

    deadline = time.monotonic() + timeout_seconds
    last_text = ""
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        if path.is_file():
            text = read_text(path)
            if text.strip():
                if text != last_text:
                    last_text = text
                    last_change = time.monotonic()
                elif time.monotonic() - last_change >= stable_seconds:
                    return text
        time.sleep(poll_seconds)
    raise TimeoutError(
        f"timed out after {timeout_seconds}s waiting for nonempty {path}"
    )
