from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..adapters.claude_cli import ClaudeCliAdapter
from ..adapters.codex_app import CodexAppServerAdapter
from ..adapters.codex_cli import CodexCliAdapter
from ..adapters.manual import ManualAdapter
from ..layout import LAYOUT_MISSING_MESSAGE, layout_ready
from ..paths import find_repo_root, project_paths
from ..runner.engine import advance, new_run_id
from ..runner.model import RunState, touch_state
from ..runner.state_store import load_run_state, save_run_state
from ..spoon_config import load_spoon_config
from ..task_label import conversation_title, resolve_task_label


def register(subparsers):
    parser = subparsers.add_parser(
        "run", help="Advance the workflow runner by one phase.")
    parser.add_argument("--repo", type=Path,
                        default=Path.cwd(), help="Repository path.")
    parser.add_argument(
        "--continue",
        dest="continue_run",
        action="store_true",
        help="Continue an existing run-state.json.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Short requirement label for conversation titles (Spoon:<label>). "
        "Defaults to brief Goal, then persists on the run.",
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON.")
    parser.set_defaults(handler=run)


def runner_payload(result) -> dict[str, object]:
    return {
        "exit_code": result.exit_code,
        "phase": result.state.phase.value,
        "status": result.state.status.value,
        "pending_decision": result.state.pending_decision,
        "task_label": result.state.task_label,
        "actions": [action.to_dict() for action in result.actions],
    }


def ensure_task_label(
    paths,
    state: RunState,
    *,
    label_override: str | None = None,
) -> RunState:
    label = resolve_task_label(
        paths,
        override=label_override,
        existing=state.task_label,
    )
    if state.task_label == label:
        return state
    updated = touch_state(state, task_label=label)
    save_run_state(paths, updated)
    return updated


def build_adapters(
    repo: Path,
    *,
    title: str,
    run_id: str,
) -> dict[str, object]:
    paths = project_paths(repo)
    config = load_spoon_config(paths)
    adapters: dict[str, object] = {
        "manual": ManualAdapter(),
    }
    claude = config.agents.claude
    codex = config.agents.codex
    if claude.cli:
        adapters["claude_review"] = ClaudeCliAdapter(
            model=claude.model,
            conversation_title=title,
            visible=config.visible_terminals,
            terminal=config.terminal,
            ui=claude.ui,
            session_key=run_id,
        )
    if codex.cli:
        adapters["codex_thread_message"] = CodexCliAdapter(
            model=codex.model,
            reasoning_effort=codex.reasoning_effort,
            service_tier=codex.service_tier,
            visible=config.visible_terminals,
        )
    elif codex.desktop:
        adapters["codex_thread_message"] = CodexAppServerAdapter(
            project_map=codex.project_map,
            model=codex.model,
            reasoning_effort=codex.reasoning_effort,
            service_tier=codex.service_tier,
            conversation_title=title,
            thread_key=run_id,
        )
    return adapters


def _human_action_summary(result) -> str | None:
    if not result.actions:
        return None
    kinds = ", ".join(sorted({action.kind.value for action in result.actions}))
    if result.exit_code == 11:
        return f"host action pending: {kinds}"
    if result.exit_code == 20:
        return f"manual fallback pending: {kinds}"
    return f"actions: {kinds}"


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    if not layout_ready(paths):
        print(LAYOUT_MISSING_MESSAGE, flush=True)
        return 2
    if args.continue_run:
        if not paths.run_state.exists():
            print("run-state.json is missing; cannot continue.", flush=True)
            return 2
    elif not paths.run_state.exists():
        state = RunState.new(new_run_id())
        save_run_state(paths, state)

    state = load_run_state(paths)
    state = ensure_task_label(
        paths, state, label_override=getattr(args, "label", None))
    title = conversation_title(state.task_label or "current")
    adapters = build_adapters(repo, title=title, run_id=state.run_id)
    result = advance(repo, adapters)
    if args.json:
        print(json.dumps(runner_payload(result), ensure_ascii=False, indent=2))
    else:
        summary = _human_action_summary(result)
        if summary:
            print(summary, flush=True)
        print(
            f"phase={result.state.phase.value} status={result.state.status.value} "
            f"exit={result.exit_code} title={title}",
            flush=True,
        )
        if result.state.pending_decision:
            print(
                f"pending_decision={result.state.pending_decision}", flush=True)
    return int(result.exit_code)
