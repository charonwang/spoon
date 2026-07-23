from __future__ import annotations

from argparse import Namespace

from ..skills_install import (
    SKILL_DIR_NAME,
    bundled_skill_dir,
    default_skill_link_targets,
    install_user_skills,
)


def register(subparsers):
    parser = subparsers.add_parser(
        "skills",
        help="Install or inspect the user-level Spoon skill symlinks.",
    )
    sub = parser.add_subparsers(dest="skills_command", required=True)

    install = sub.add_parser(
        "install",
        help=(
            f"Symlink skills/{SKILL_DIR_NAME} into ~/.agents/skills and "
            "~/.claude/skills (Cursor + Claude Code)."
        ),
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing symlink or directory at the target path.",
    )
    install.set_defaults(handler=run_install)

    status = sub.add_parser(
        "status",
        help="Show bundled skill source and user-level link targets.",
    )
    status.set_defaults(handler=run_status)


def run_install(args: Namespace) -> int:
    results = install_user_skills(force=args.force)
    for link, status in results:
        print(f"{status}\t{link}")
    return 0


def run_status(args: Namespace) -> int:
    del args
    source = bundled_skill_dir()
    print(f"source\t{source if source is not None else '(missing)'}")
    for link in default_skill_link_targets():
        if link.is_symlink():
            print(f"symlink\t{link}\t->\t{link.resolve()}")
        elif link.exists():
            kind = "directory" if link.is_dir() else "file"
            print(f"{kind}\t{link}")
        else:
            print(f"missing\t{link}")
    return 0
