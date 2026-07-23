from __future__ import annotations

import os
import shutil
from pathlib import Path


SKILL_DIR_NAME = "spoon"


def bundled_skill_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / SKILL_DIR_NAME / "SKILL.md"
        if candidate.is_file():
            return candidate.parent
    return None


def default_skill_link_targets() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills" / SKILL_DIR_NAME,
        home / ".claude" / "skills" / SKILL_DIR_NAME,
    ]


def _path_state(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    return "file"


def _normalize_path(path: Path) -> Path:
    text = str(path.resolve())
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text)


def install_skill_symlink(
    link: Path,
    source: Path,
    *,
    force: bool = False,
) -> str:
    """Create or refresh a directory symlink. Returns a short status token."""
    source = _normalize_path(source)
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"skill source missing SKILL.md: {source}")

    state = _path_state(link)
    if state == "symlink":
        current = Path(os.readlink(link))
        if not current.is_absolute():
            current = link.parent / current
        current = _normalize_path(current)
        if current == source and not force:
            return "ok"
        if not force:
            raise FileExistsError(
                f"{link} already points to {current}; pass --force to replace"
            )
        link.unlink()
    elif state in {"directory", "file"}:
        if not force:
            raise FileExistsError(
                f"{link} exists as a {state}; pass --force to replace"
            )
        if state == "directory":
            shutil.rmtree(link)
        else:
            link.unlink()

    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        raise OSError(
            f"could not create symlink {link} -> {source}: {exc}. "
            "On Windows, enable Developer Mode or run with symlink privilege."
        ) from exc
    return "installed"


def install_user_skills(
    *,
    force: bool = False,
    targets: list[Path] | None = None,
    source: Path | None = None,
) -> list[tuple[Path, str]]:
    skill_source = source if source is not None else bundled_skill_dir()
    if skill_source is None:
        raise FileNotFoundError(
            f"bundled skill not found (expected skills/{SKILL_DIR_NAME}/SKILL.md)"
        )
    links = targets if targets is not None else default_skill_link_targets()
    results: list[tuple[Path, str]] = []
    for link in links:
        results.append(
            (link, install_skill_symlink(link, skill_source, force=force))
        )
    return results
