from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..io_util import write_text
from ..paths import find_repo_root, project_paths
from ..templates import prompt_templates


def register(subparsers):
    parser = subparsers.add_parser("prompts", help="Generate prompt files.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def generate_prompts(repo: Path) -> None:
    paths = project_paths(repo)
    paths.prompts.mkdir(parents=True, exist_ok=True)
    for filename, content in prompt_templates().items():
        write_text(paths.prompts / filename, content)


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    generate_prompts(repo)
    print(f"Prompts written to {project_paths(repo).prompts}")
    return 0
