from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ..adapters.manual import ManualAdapter
from ..paths import find_repo_root, project_paths
from ..runner.engine import advance, new_run_id
from ..runner.model import RunState
from ..runner.state_store import load_run_state, save_run_state


def register(subparsers):
    parser = subparsers.add_parser("run", help="Advance the V2 workflow runner by one phase.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.add_argument(
        "--continue",
        dest="continue_run",
        action="store_true",
        help="Continue an existing run-state.json.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.set_defaults(handler=run)


def runner_payload(result) -> dict[str, object]:
    return {
        "exit_code": result.exit_code,
        "phase": result.state.phase.value,
        "status": result.state.status.value,
        "pending_decision": result.state.pending_decision,
        "actions": [action.to_dict() for action in result.actions],
    }


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    if args.continue_run:
        if not paths.run_state.exists():
            print("run-state.json is missing; cannot continue.", flush=True)
            return 2
    elif not paths.run_state.exists():
        state = RunState.new(new_run_id())
        save_run_state(paths, state)

    result = advance(repo, {"manual": ManualAdapter()})
    if args.json:
        print(json.dumps(runner_payload(result), ensure_ascii=False, indent=2))
    else:
        print(
            f"phase={result.state.phase.value} status={result.state.status.value} "
            f"exit={result.exit_code}"
        )
    return int(result.exit_code)
