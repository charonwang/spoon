from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..config_ack import acknowledge_config, config_ack_status, format_confirmation_line
from ..config_report import format_config_keys, render_config_show
from ..paths import find_repo_root, project_paths


def register(subparsers):
    parser = subparsers.add_parser(
        "config",
        help="Inspect Spoon project configuration and tool availability.",
    )
    sub = parser.add_subparsers(dest="config_command", required=True)
    show = sub.add_parser(
        "show",
        help="Print config summary plus Claude/Codex environment notes.",
    )
    show.add_argument("--repo", type=Path,
                      default=Path.cwd(), help="Repository path.")
    show.set_defaults(handler=run_show)

    keys = sub.add_parser(
        "keys",
        help="List .spoon/config.json keys, defaults, and allowed values.",
    )
    keys.set_defaults(handler=run_keys)

    ack = sub.add_parser(
        "ack",
        help="Record that the current .spoon/config.json was confirmed.",
    )
    ack.add_argument("--repo", type=Path,
                     default=Path.cwd(), help="Repository path.")
    ack.set_defaults(handler=run_ack)


def run_show(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    print(render_config_show(paths), end="")
    status = config_ack_status(paths)
    print(format_confirmation_line(status), flush=True)
    return 0


def run_keys(args: Namespace) -> int:
    del args
    print(format_config_keys(), end="")
    return 0


def run_ack(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    status = acknowledge_config(paths)
    print(format_confirmation_line(status), flush=True)
    print("Recorded config confirmation.", flush=True)
    return 0
