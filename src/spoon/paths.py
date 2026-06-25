from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import SPOON_DIR, CURRENT_DIR, PROMPTS_DIR, REVIEWS_DIR, SNAPSHOTS_DIR


@dataclass(frozen=True)
class ProjectPaths:
    repo: Path
    spoon: Path
    current: Path
    prompts: Path
    reviews: Path
    snapshots: Path
    brief: Path
    plan: Path
    review_board: Path
    handoff: Path
    metadata: Path
    run_state: Path
    actions: Path
    events: Path
    implementation: Path
    config: Path


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            raise FileNotFoundError(f"No git repository found from {start}")
        current = current.parent


def project_paths(repo: Path) -> ProjectPaths:
    repo = repo.resolve()
    spoon = repo / SPOON_DIR
    current = spoon / CURRENT_DIR
    return ProjectPaths(
        repo=repo,
        spoon=spoon,
        current=current,
        prompts=current / PROMPTS_DIR,
        reviews=current / REVIEWS_DIR,
        snapshots=current / SNAPSHOTS_DIR,
        brief=current / "brief.md",
        plan=current / "plan.md",
        review_board=current / "review-board.md",
        handoff=current / "handoff.md",
        metadata=current / "metadata.json",
        run_state=current / "run-state.json",
        actions=current / "actions.json",
        events=current / "events.jsonl",
        implementation=current / "implementation.json",
        config=spoon / "config.json",
    )
