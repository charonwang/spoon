from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .adapters.command_util import find_executable
from .adapters.terminal_launch import resolve_terminal
from .paths import ProjectPaths
from .spoon_config import (
    CLAUDE_UI_MODES,
    CODEX_REASONING_EFFORTS,
    TERMINAL_LAUNCHERS,
    SpoonConfig,
    TerminalConfig,
    load_spoon_config,
)


@dataclass(frozen=True)
class ToolProbe:
    name: str
    command: str
    path: str | None

    @property
    def available(self) -> bool:
        return self.path is not None


def probe_tools(
    *,
    claude_command: str = "claude",
    codex_command: str = "codex",
) -> dict[str, ToolProbe]:
    return {
        "claude": ToolProbe(
            name="Claude Code CLI",
            command=claude_command,
            path=find_executable(claude_command),
        ),
        "codex": ToolProbe(
            name="Codex CLI",
            command=codex_command,
            path=find_executable(codex_command),
        ),
    }


def _fmt(value: object) -> str:
    if value is None:
        return "(unset)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value)


def format_config_show(
    config: SpoonConfig,
    probes: dict[str, ToolProbe],
    *,
    terminal_note: str | None = None,
) -> str:
    claude = config.agents.claude
    codex = config.agents.codex
    claude_probe = probes["claude"]
    codex_probe = probes["codex"]
    term = config.terminal

    lines = [
        "Config (.spoon/config.json)",
        f"  language: {_fmt(config.language)}",
        f"  visible_terminals: {_fmt(config.visible_terminals)}",
        f"  experimental_cursor_ui: {_fmt(config.experimental_cursor_ui)}",
        "  terminal:",
        f"    launcher: {_fmt(term.launcher)}",
        f"    executable: {_fmt(term.executable)}",
        f"    args: {_fmt(term.args)}",
        "  agents.claude:",
        f"    cli: {_fmt(claude.cli)}",
        f"    model: {_fmt(claude.model)}",
        f"    ui: {_fmt(claude.ui)}",
        "  agents.codex:",
        f"    cli: {_fmt(codex.cli)}",
        f"    desktop: {_fmt(codex.desktop)}",
        f"    model: {_fmt(codex.model)}",
        f"    reasoning_effort: {_fmt(codex.reasoning_effort)}",
        f"    service_tier: {_fmt(codex.service_tier)}",
        "",
        "Environment",
    ]

    if claude_probe.available:
        lines.append(
            f"  Claude Code CLI ({claude_probe.command}): found ({claude_probe.path})"
        )
    else:
        lines.append(
            f"  Claude Code CLI ({claude_probe.command}): not installed or not on PATH"
        )

    if codex_probe.available:
        lines.append(
            f"  Codex CLI ({codex_probe.command}): found ({codex_probe.path})"
        )
        lines.append(
            "  Codex Desktop: CLI present; Desktop is launched via `codex app` "
            "(confirm the Desktop app is installed locally)"
        )
    else:
        lines.append(
            f"  Codex CLI ({codex_probe.command}): not installed or not on PATH"
        )
        lines.append(
            "  Codex Desktop: not confirmed (Codex CLI missing; "
            "`codex app` / app-server unavailable)"
        )

    if terminal_note is None:
        probe_term = (
            term
            if config.visible_terminals
            else TerminalConfig(launcher="inline")
        )
        resolved = resolve_terminal(
            probe_term,
            cwd=Path.cwd(),
            job_path=Path.cwd() / ".spoon-terminal-probe-job.json",
        )
        terminal_note = resolved.note
    lines.append(f"  Visible Claude terminal: {terminal_note}")
    if not config.visible_terminals:
        lines.append(
            "  (visible_terminals is false; Claude runs quietly with no live stream)"
        )
    elif term.launcher == "inline":
        lines.append(
            "  (inline = Spoon/Cursor agent output; cannot open Cursor's Terminal panel)"
        )

    lines.append("")
    lines.append("Notes")
    notes: list[str] = []
    if claude.cli and not claude_probe.available:
        notes.append(
            "- agents.claude.cli is true, but Claude Code CLI was not found."
        )
    elif not claude.cli:
        notes.append(
            "- agents.claude.cli is false; Claude review will not run.")

    if codex.cli and not codex_probe.available:
        notes.append(
            "- agents.codex.cli is true, but Codex CLI was not found."
        )
    elif codex.desktop and not codex_probe.available:
        notes.append(
            "- agents.codex.desktop is true, but Codex CLI/Desktop tooling "
            "was not found; desktop review may be unavailable."
        )
    elif not codex.cli and not codex.desktop:
        notes.append(
            "- agents.codex.cli and agents.codex.desktop are false; "
            "Codex review will not run."
        )
    elif codex.cli:
        notes.append(
            "- agents.codex.cli is true; Codex CLI path will be used.")
    elif codex.desktop:
        notes.append(
            "- agents.codex.desktop is true; Spoon will use Codex Desktop "
            "via app-server."
        )

    if config.visible_terminals and term.launcher != "inline":
        if claude.ui == "interactive":
            notes.append(
                "- visible_terminals + agents.claude.ui=interactive opens Claude "
                f"Code TUI in an external terminal ({term.launcher}); Spoon waits "
                "for the review file and resumes the same session on later turns."
            )
        else:
            notes.append(
                "- visible_terminals opens Claude in an external terminal "
                f"({term.launcher}); print/stream-json output is captured by Spoon."
            )

    if not notes:
        notes.append("- No config/environment mismatches detected.")
    lines.extend(notes)
    lines.append("")
    lines.append(
        "Edit .spoon/config.json if needed, re-run `spoon config show`, "
        "then `spoon config ack` (or confirm in /spoon) to continue."
    )
    return "\n".join(lines) + "\n"


def render_config_show(paths: ProjectPaths) -> str:
    config = load_spoon_config(paths)
    return format_config_show(config, probe_tools())


def format_config_keys() -> str:
    """Document .spoon/config.json keys for end users (no repo required)."""
    launchers = ", ".join(sorted(TERMINAL_LAUNCHERS))
    efforts = ", ".join(sorted(CODEX_REASONING_EFFORTS))
    claude_uis = ", ".join(sorted(CLAUDE_UI_MODES))
    lines = [
        "Spoon config keys (.spoon/config.json)",
        "",
        "Top-level",
        "  language                 string   default auto",
        "                           auto = follow brief/plan language; or a tag like zh-CN",
        "  visible_terminals        bool     default false",
        "                           true = show Claude review live (see terminal.*)",
        "  experimental_cursor_ui   bool     default false",
        "                           true = allow Cursor Plan/Agent UI automation",
        "",
        "terminal (Claude visible display when visible_terminals is true)",
        "  terminal.launcher        string   default windows_terminal",
        f"                           one of: {launchers}",
        "                           inline = stream into spoon process (not Cursor's Terminal panel)",
        "                           windows_terminal / pwsh / conhost / tabby = external window",
        "                           pwsh = PowerShell 7 new console (-NoExit, runs inner command)",
        "                           custom = requires executable + args",
        "  terminal.executable      string|null   override launcher binary (PATH or absolute)",
        "  terminal.args            string[]|null required for custom; placeholders {cwd} {script}",
        "",
        "agents.claude",
        "  agents.claude.cli        bool     default true   run Claude via spoon adapter",
        "  agents.claude.model      string|null   Claude --model; null = Claude default",
        f"  agents.claude.ui         string   default interactive   one of: {claude_uis}",
        "                           interactive = Claude Code TUI + --session-id/--resume",
        "                           print = non-interactive -p JSON/stream-json (legacy)",
        "",
        "agents.codex",
        "  agents.codex.cli         bool     default false  Codex CLI path",
        "  agents.codex.desktop     bool     default false  Codex Desktop / app-server",
        "  agents.codex.model       string|null",
        f"  agents.codex.reasoning_effort  string|null   one of: {efforts}",
        "  agents.codex.service_tier       string|null   e.g. default, fast",
        "  agents.codex.project_map        object        cwd remaps for Desktop",
        "",
        "Inspect this repo:  spoon config show",
        "Confirm config:     spoon config ack",
        "List these keys:    spoon config keys",
    ]
    return "\n".join(lines) + "\n"
