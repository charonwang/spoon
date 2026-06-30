CURRENT_DIR = "current"
SPOON_DIR = ".spoon"
PROMPTS_DIR = "prompts"
REVIEWS_DIR = "reviews"
SNAPSHOTS_DIR = "snapshots"

GENERATED_START = "<!-- spoon:generated-findings:start -->"
GENERATED_END = "<!-- spoon:generated-findings:end -->"

BOARD_HEADING_ACCEPTED = "### Accepted For Handoff"
BOARD_HEADING_PARKED = "### Parked"
BOARD_HEADING_REJECTED = "### Rejected"

PROMPT_FILES = [
    "cursor-plan.md",
    "cursor-implement.md",
    "codex-plan-review.md",
    "claude-plan-review.md",
    "codex-code-review.md",
    "claude-code-review.md",
    "final-plan-review.md",
    "final-check.md",
    "commit-message.md",
]

REVIEW_FILES = [
    "codex-plan.md",
    "claude-plan.md",
    "final-plan-review.md",
    "cursor-self-review.md",
    "codex-code.md",
    "claude-code.md",
]

SNAPSHOT_FILES = [
    "status.txt",
    "diff-stat.txt",
    "diff.patch",
    "recent-commits.txt",
    "test-output.txt",
    "dependency-check.txt",
    "sensitive-scan.txt",
    "plan-sources.txt",
]
