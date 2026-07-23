from __future__ import annotations

from dataclasses import dataclass, field

from .io_util import read_json
from .paths import ProjectPaths

CODEX_REASONING_EFFORTS = frozenset(
    {
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "ultra",
        "max",
    }
)

TERMINAL_LAUNCHERS = frozenset(
    {
        "inline",
        "windows_terminal",
        "conhost",
        "pwsh",
        "tabby",
        "custom",
    }
)

CLAUDE_UI_MODES = frozenset({"interactive", "print"})

# Pre-agents flat keys; configs must use agents.* instead.
_REMOVED_FLAT_KEYS = frozenset(
    {
        "claude_cli",
        "claude_model",
        "codex_cli",
        "codex_desktop",
        "codex_model",
        "codex_reasoning_effort",
        "codex_service_tier",
        "codex_project_map",
    }
)


class SpoonConfigError(Exception):
    """Raised when .spoon/config.json is present but invalid."""


@dataclass(frozen=True)
class ClaudeAgentConfig:
    cli: bool = True
    model: str | None = None
    # interactive = Claude Code TUI (+ --resume); print = -p JSON/stream-json.
    ui: str = "interactive"


@dataclass(frozen=True)
class CodexAgentConfig:
    cli: bool = False
    desktop: bool = False
    model: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    project_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentsConfig:
    claude: ClaudeAgentConfig = field(default_factory=ClaudeAgentConfig)
    codex: CodexAgentConfig = field(default_factory=CodexAgentConfig)


@dataclass(frozen=True)
class TerminalConfig:
    launcher: str = "windows_terminal"
    executable: str | None = None
    args: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SpoonConfig:
    experimental_cursor_ui: bool = False
    visible_terminals: bool = False
    language: str = "auto"
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)


def _as_bool(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    raise SpoonConfigError(f"config key {key!r} must be a boolean")


def _as_language(value: object, key: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise SpoonConfigError(
        f"config key {key!r} must be a non-empty string (use \"auto\" or a tag like zh-CN)"
    )


def _as_optional_str(value: object, key: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    raise SpoonConfigError(f"config key {key!r} must be a string or null")


def _as_reasoning_effort(value: object, key: str) -> str | None:
    text = _as_optional_str(value, key)
    if text is None:
        return None
    lowered = text.lower()
    if lowered not in CODEX_REASONING_EFFORTS:
        allowed = ", ".join(sorted(CODEX_REASONING_EFFORTS))
        raise SpoonConfigError(
            f"config key {key!r} must be one of: {allowed}"
        )
    return lowered


def _as_str_map(value: object, key: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SpoonConfigError(f"config key {key!r} must be an object")
    result: dict[str, str] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not isinstance(item_value, str):
            raise SpoonConfigError(
                f"config key {key!r} must map strings to strings")
        result[item_key] = item_value
    return result


def _as_object(value: object, key: str) -> dict:
    if not isinstance(value, dict):
        raise SpoonConfigError(f"config key {key!r} must be an object")
    return value


def _as_str_list(value: object, key: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise SpoonConfigError(
            f"config key {key!r} must be an array of strings or null")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise SpoonConfigError(
                f"config key {key!r} must be an array of strings or null")
        result.append(item)
    return tuple(result)


def _parse_terminal(raw: object) -> TerminalConfig:
    if raw is None:
        return TerminalConfig()
    data = _as_object(raw, "terminal")
    launcher = _as_optional_str(data.get("launcher"), "terminal.launcher")
    if launcher is None:
        launcher = "windows_terminal"
    launcher = launcher.strip().lower()
    if launcher not in TERMINAL_LAUNCHERS:
        allowed = ", ".join(sorted(TERMINAL_LAUNCHERS))
        raise SpoonConfigError(
            f"config key 'terminal.launcher' must be one of: {allowed}"
        )
    executable = _as_optional_str(
        data.get("executable"), "terminal.executable")
    args = _as_str_list(data.get("args"), "terminal.args")
    if launcher == "custom" and not executable:
        raise SpoonConfigError(
            "config key 'terminal.executable' is required when launcher is 'custom'"
        )
    if launcher == "custom" and not args:
        raise SpoonConfigError(
            "config key 'terminal.args' is required when launcher is 'custom' "
            "(use placeholders {cwd} and {script})"
        )
    return TerminalConfig(launcher=launcher, executable=executable, args=args)


def _as_claude_ui(value: object, key: str) -> str:
    text = _as_optional_str(value, key)
    if text is None:
        return "interactive"
    lowered = text.lower()
    if lowered not in CLAUDE_UI_MODES:
        allowed = ", ".join(sorted(CLAUDE_UI_MODES))
        raise SpoonConfigError(f"config key {key!r} must be one of: {allowed}")
    return lowered


def _parse_claude_agent(raw: dict, prefix: str) -> ClaudeAgentConfig:
    return ClaudeAgentConfig(
        cli=_as_bool(raw.get("cli", True), f"{prefix}.cli"),
        model=_as_optional_str(raw.get("model"), f"{prefix}.model"),
        ui=_as_claude_ui(raw.get("ui", "interactive"), f"{prefix}.ui"),
    )


def _parse_codex_agent(raw: dict, prefix: str) -> CodexAgentConfig:
    return CodexAgentConfig(
        cli=_as_bool(raw.get("cli", False), f"{prefix}.cli"),
        desktop=_as_bool(raw.get("desktop", False), f"{prefix}.desktop"),
        model=_as_optional_str(raw.get("model"), f"{prefix}.model"),
        reasoning_effort=_as_reasoning_effort(
            raw.get("reasoning_effort"),
            f"{prefix}.reasoning_effort",
        ),
        service_tier=_as_optional_str(
            raw.get("service_tier"),
            f"{prefix}.service_tier",
        ),
        project_map=_as_str_map(
            raw.get("project_map", {}),
            f"{prefix}.project_map",
        ),
    )


def _parse_agents(raw: object) -> AgentsConfig:
    agents_raw = _as_object(raw, "agents")
    claude = ClaudeAgentConfig()
    codex = CodexAgentConfig()
    if "claude" in agents_raw:
        claude = _parse_claude_agent(
            _as_object(agents_raw["claude"], "agents.claude"),
            "agents.claude",
        )
    if "codex" in agents_raw:
        codex = _parse_codex_agent(
            _as_object(agents_raw["codex"], "agents.codex"),
            "agents.codex",
        )
    return AgentsConfig(claude=claude, codex=codex)


def load_spoon_config(paths: ProjectPaths) -> SpoonConfig:
    if not paths.config.exists():
        return SpoonConfig()
    raw = read_json(paths.config)
    if not isinstance(raw, dict):
        raise SpoonConfigError("config must be a JSON object")

    removed = sorted(key for key in _REMOVED_FLAT_KEYS if key in raw)
    if removed:
        raise SpoonConfigError(
            "removed flat config keys; move under 'agents': "
            + ", ".join(removed)
        )

    agents = AgentsConfig()
    if "agents" in raw:
        agents = _parse_agents(raw["agents"])

    terminal = TerminalConfig()
    if "terminal" in raw:
        terminal = _parse_terminal(raw["terminal"])

    return SpoonConfig(
        experimental_cursor_ui=_as_bool(
            raw.get("experimental_cursor_ui", False),
            "experimental_cursor_ui",
        ),
        visible_terminals=_as_bool(
            raw.get("visible_terminals", False),
            "visible_terminals",
        ),
        language=_as_language(raw.get("language", "auto"), "language"),
        agents=agents,
        terminal=terminal,
    )
