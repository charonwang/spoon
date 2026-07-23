from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ..io_util import read_text, write_text
from ..layout import LAYOUT_MISSING_MESSAGE, layout_ready
from ..locale_util import resolve_language_tag
from ..paths import find_repo_root, project_paths
from ..spoon_config import load_spoon_config
from ..templates import prompt_templates


def register(subparsers):
    parser = subparsers.add_parser("prompts", help="Generate prompt files.")
    parser.add_argument("--repo", type=Path,
                        default=Path.cwd(), help="Repository path.")
    parser.set_defaults(handler=run)


def generate_prompts(repo: Path) -> None:
    paths = project_paths(repo)
    config = load_spoon_config(paths)
    brief_text = read_text(paths.brief) if paths.brief.is_file() else ""
    plan_text = read_text(paths.plan) if paths.plan.is_file() else ""
    language_tag = resolve_language_tag(
        config.language,
        brief_text=brief_text,
        plan_text=plan_text,
    )
    paths.prompts.mkdir(parents=True, exist_ok=True)
    for filename, content in prompt_templates(language_tag).items():
        write_text(paths.prompts / filename, content)


def run(args: Namespace) -> int:
    repo = find_repo_root(args.repo)
    paths = project_paths(repo)
    if not layout_ready(paths):
        print(LAYOUT_MISSING_MESSAGE, flush=True)
        return 2
    generate_prompts(repo)
    print(f"Prompts written to {paths.prompts}")
    return 0
