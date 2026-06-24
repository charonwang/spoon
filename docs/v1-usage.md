# Spoon V1 Usage Guide

Spoon V1 is a **semi-automated file workflow**. It maintains Markdown and snapshot files under `.spoon/current/` in your business repository. It does **not** modify application code, run agents for you, or create Git commits.

You, Cursor, Codex, and Claude Code read the same files and coordinate manually. V1 has no `spoon run` orchestrator (that is V2).

## Requirements

- Python 3.11 or newer
- Git
- A local checkout of [Spoon](https://github.com/charonwang/spoon)

## One-Time Install

```powershell
cd D:\Charon\Project\Spoon
python -m pip install -e .
spoon --help
```

If `spoon` is not on your `PATH`, use `python -m spoon` instead.

After moving or cloning Spoon to a new path, reinstall:

```powershell
cd <spoon-checkout>
python -m pip install -e .
```

## Initialize a Business Repository

Run from the **root of the Git repository** you want to manage (or pass `--repo`):

```powershell
cd D:\path\to\your-repo
spoon init
```

This creates `.spoon/current/` and adds `.spoon/` to `.git/info/exclude` so workflow files stay local without changing `.gitignore`.

## End-to-End Workflow

```text
brief → plan → plan review → board decisions → handoff → implement → code review → final check → archive
```

| Step | You | Spoon |
| --- | --- | --- |
| 1 | Write `.spoon/current/brief.md` | — |
| 2 | Create a plan in Cursor; adopt it | `spoon adopt-plan` |
| 3 | Refresh evidence before reviews | `spoon snapshot` |
| 4 | Copy prompts into AI tools | `spoon prompts` |
| 5 | Save review outputs under `reviews/` | — |
| 6 | Summarize findings | `spoon board` |
| 7 | Move accepted items in the board | — (manual) |
| 8 | Generate implementation handoff | `spoon handoff` |
| 9 | Implement in Cursor; repeat review cycle | `spoon snapshot`, `spoon board`, … |
| 10 | Archive when done | `spoon archive` |

## Step-by-Step

### 1. Write the task brief

Edit `.spoon/current/brief.md` with goals, constraints, and out-of-scope items.

### 2. Adopt a Cursor plan

After creating or exporting a Cursor plan:

```powershell
spoon adopt-plan --source "C:\path\to\cursor.plan.md"
spoon adopt-plan --source ".\plan.md" --replace
```

The canonical plan lives at `.spoon/current/plan.md`.

**Cursor link format (Windows):** use file URI anchors in plans:

```text
file:///D:/path/to/your/repo/internal/file.go#L82
```

Avoid raw paths such as `C:\path\file.go:82` or `C:/path/file.go:82`.

### 3. Capture snapshots

```powershell
spoon snapshot --test-cmd "python -m unittest discover -s tests -p \"test_*.py\""
spoon snapshot --dependency-cmd "go mod verify"
```

Writes under `.spoon/current/snapshots/`:

- `status.txt` — Git status including untracked files
- `diff-stat.txt`, `diff.patch` — unstaged, staged, and untracked sections
- `test-output.txt`, `dependency-check.txt`, `sensitive-scan.txt`
- recent commit metadata

Re-run `snapshot` after code or test changes. Snapshot writes are sequential, not transactional; rerun if interrupted.

### 4. Generate review prompts

```powershell
spoon prompts
```

Files appear in `.spoon/current/prompts/`:

| File | Use with |
| --- | --- |
| `cursor-plan.md` | Cursor — create or revise the plan |
| `codex-plan-review.md` | Codex — plan review |
| `claude-plan-review.md` | Claude Code — plan review |
| `cursor-implement.md` | Cursor — implement from handoff |
| `codex-code-review.md` | Codex — code review |
| `claude-code-review.md` | Claude Code — code review |
| `final-plan-review.md` | Independent final plan review |
| `final-check.md` | Pre-merge / pre-release checks |
| `commit-message.md` | Draft commit message from snapshots and handoff |

Copy the prompt into your AI tool and reference files under `.spoon/current/` (for example with `@` in Cursor).

### 5. Collect review outputs

Save each tool's output under `.spoon/current/reviews/`, for example:

```text
reviews/cursor-plan.md
reviews/codex-plan.md
reviews/claude-plan.md
```

Filenames are flexible; Spoon reads whatever is in that directory.

### 6. Summarize into the review board

```powershell
spoon board
```

Updates the generated sections of `.spoon/current/review-board.md`. **You** edit the human sections—especially `Accepted For Handoff`. Resolve or explicitly defer items in `Blocking` and `Needs Triage` before implementation.

### 7. Generate the implementation handoff

```powershell
spoon handoff
```

Creates `.spoon/current/handoff.md` from accepted board items. In Cursor, use `prompts/cursor-implement.md` together with `handoff.md` and `plan.md`.

### 8. After implementation — review again

```powershell
spoon snapshot --test-cmd "..."
spoon prompts
```

Save new reviews → `spoon board` → your decisions → `spoon handoff` if needed.

### 9. Archive the completed task

```powershell
spoon archive --archive-root "D:\Charon\Project\archives" --project my-project --task my-task-name
```

Moves the current task into `<archive-root>/<project>/<timestamp>-<task>/` and recreates an empty `.spoon/current/` for the next task.

Example layout:

```text
D:\Charon\Project\archives\
  my-project\
    2026-06-24-my-task-name\
      brief.md
      plan.md
      review-board.md
      ...
```

## Command Reference

All commands accept `--repo PATH` when you are not in the repository directory:

```powershell
spoon snapshot --repo "D:\path\to\repo" --test-cmd "pytest -q"
```

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/` and exclude `.spoon/` |
| `spoon adopt-plan --source PATH` | Move plan into `plan.md` |
| `spoon snapshot` | Refresh Git and command snapshots |
| `spoon prompts` | Write prompt templates |
| `spoon board` | Summarize `reviews/` into `review-board.md` |
| `spoon handoff` | Build `handoff.md` from accepted items |
| `spoon archive` | Archive task; requires `--archive-root`, `--project`, `--task` |

## What Spoon Does Not Do (V1)

- Stage, commit, or push business code
- Read private chat logs or editor internals
- Auto-accept or auto-reject review findings
- Orchestrate tools automatically (no `spoon run` yet)

Final review judgment and Git operations remain yours.

## Migrating From `.ai-flow/`

If an early draft used `.ai-flow/`:

```powershell
Rename-Item .ai-flow .spoon
```

Ensure `.git/info/exclude` contains:

```text
.spoon/
```

Spoon does not maintain dual compatibility with `.ai-flow/`.

## Related Docs

- [Design overview](design-overview.md) — V1 scope and commands
- [Roadmap](roadmap.md) — V2 orchestrator plans
