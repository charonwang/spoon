# Spoon Usage Guide

Spoon is a **local file workflow CLI**. It maintains Markdown and snapshot files under `.spoon/current/` in your business repository. It does **not** modify application code or create Git commits.

You, Cursor, Codex, and Claude Code read the same files. For automated phase advancement, use `spoon run` and the `spoon-orchestrator` Skill (see [architecture](architecture.md) and [host actions](host-actions.md)).

Generated implementation prompts may allow your coding agent to create a local checkpoint commit
after a completed approved item or review-fix batch passes relevant verification. Spoon and its host
actions still do not stage, commit, or push; checkpoint commits are local coding-agent recovery
points and must not be pushed unless you explicitly ask.

## Requirements

- Python 3.11 or newer
- Git
- A local checkout of [Spoon](https://github.com/charonwang/spoon)

## One-Time Install

Spoon requires **Python 3.11+**. Python 3.12+ no longer bundles pip — use `venv` (which includes pip) or bootstrap with `ensurepip`.

> Examples use Windows PowerShell. On macOS/Linux, replace `\` path separators with `/` and use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

### With venv (recommended)

```powershell
cd <spoon-checkout>
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m spoon --help
```

To use `spoon` directly without the full path, activate the venv:

```powershell
.venv\Scripts\activate
spoon --help
```

### With uv

```powershell
cd <spoon-checkout>
uv venv --python ">=3.11"
uv pip install -e .
.\.venv\Scripts\python.exe -m spoon --help
```

### Global install with uv (no venv, runs from any directory)

`uv tool install` exposes `spoon` on your PATH (for example `~/.local/bin`), so you can run it from any business repository without activating a venv:

```powershell
uv tool install -e <spoon-checkout>                     # editable: tracks your source
uv tool install <spoon-checkout>\dist\spoon-0.2.0-py3-none-any.whl  # or from a built wheel
spoon --help
```

The editable form keeps the command bound to your checkout — if you move or delete the source directory, reinstall from the new path. Manage the tool with `uv tool list`, `uv tool upgrade spoon`, and `uv tool uninstall spoon`. If `uv` is not installed, run `irm https://astral.sh/uv/install.ps1 | iex` and restart the terminal first.

### If pip is missing (Python 3.12+)

`ensurepip` is a built-in module that bootstraps pip:

```powershell
python -m ensurepip --upgrade
python -m pip install -e .
spoon --help
```

### With the py launcher (Windows)

List installed interpreters, then pick any version `py -0p` reports as 3.11 or newer. The `py` launcher needs an exact tag such as `-3.11` or `-3.12` — it does not accept a range like `>=3.11`, so the `3.11` below is just an example:

```powershell
py -0p
py -3.11 --version
```

When `py -3.11 --version` succeeds:

```powershell
cd <spoon-checkout>
py -3.11 -m pip install -e .
spoon --help
```

If `py -3.11` is available but pip is missing:

```powershell
py -3.11 -m ensurepip --upgrade
py -3.11 -m pip install -e .
```

After moving or cloning Spoon to a new path, reinstall with the same interpreter you used initially (for example `.venv\Scripts\python -m pip install -e .` or `uv pip install -e .` in the existing `.venv`).

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

Optionally drive phase transitions with `spoon run --json` and complete host actions via `spoon action complete`.

## Step-by-Step

### 1. Write the task brief

Edit `.spoon/current/brief.md` with goals, constraints, and out-of-scope items.

### 2. Adopt a Cursor plan

After creating or exporting a Cursor plan:

```powershell
spoon adopt-plan --source "D:\path\to\cursor.plan.md"
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
spoon snapshot --test-cmd "python -m unittest discover -s tests -p \"test_*.py\"" --dependency-cmd "go mod verify"
```

`--test-cmd` and `--dependency-cmd` can be passed together (as above) or separately; omit either to skip that capture. Writes under `.spoon/current/snapshots/`.

Re-run `snapshot` after code or test changes. Each run overwrites the snapshot files. Writes are sequential, not transactional; rerun if interrupted.

When `.spoon/current/implementation-base.txt` exists, `diff-stat.txt` and `diff.patch` also include
committed checkpoint changes from that base to `HEAD`, so code review and final check can inspect
local checkpoint commits as well as unstaged, staged, and untracked files.

### 4. Generate review prompts

```powershell
spoon prompts
```

Copy the prompt into your AI tool and reference files under `.spoon/current/`.

### 5. Collect review outputs

Save each tool's output under `.spoon/current/reviews/`.

### 6. Summarize into the review board

```powershell
spoon board
```

Updates the generated sections of `.spoon/current/review-board.md`. **You** edit the human sections—especially `Accepted For Handoff`.

### 7. Generate the implementation handoff

```powershell
spoon handoff
```

Creates `.spoon/current/handoff.md` from accepted board items.

### 8. After implementation — review again

During implementation, the coding agent may check existing `plan.md` checkbox items that directly
match completed approved work. It must not add checklist items, rewrite the plan, or record review
history in `plan.md`. After the relevant verification for a completed approved item or review-fix
batch passes, it may create a local checkpoint commit. Squashing or keeping those commits is a
human or final-phase decision, not an implementation-agent task.

```powershell
spoon snapshot --test-cmd "..."
spoon prompts
```

Save new reviews → `spoon board` → your decisions → `spoon handoff` if needed.

### 9. Archive the completed task

```powershell
spoon archive --archive-root "D:\Charon\Project\archives" --project my-project --task my-task-name
```

### 10. Runner loop (optional)

`spoon run` advances at most one phase per call; loop on it (or let the `spoon-orchestrator` Skill loop) to walk the workflow. Without `--continue`, a missing `run-state.json` starts a fresh run. With `--continue`, the Runner requires an existing `run-state.json` and errors out instead of starting over — use it once a run is underway:

```powershell
spoon run --repo . --json
spoon run --repo . --continue --json
spoon action list --repo .
spoon action complete --id <id> --output .spoon/current/reviews/codex-plan.md
spoon action fail --id <id> --message "reason"
```

Exit codes: `0` stable, `10` user decision, `11` host action pending, `20` manual fallback, `21` runner failure. Full table: [architecture](architecture.md).

### 11. GitHub export (optional)

Build a redacted export candidate for human review before any push:

```powershell
spoon export-github --repo . --destination D:\exports\candidate --project my-project --task my-task
```

See [export policy](export-policy.md).

## Command Reference

This table is the canonical command list; other docs link here instead of repeating it. All commands accept `--repo PATH` when you are not in the repository directory.

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/` and exclude `.spoon/` |
| `spoon adopt-plan --source PATH` | Move plan into `plan.md` |
| `spoon snapshot` | Refresh Git and command snapshots |
| `spoon prompts` | Write prompt templates |
| `spoon board` | Summarize `reviews/` into `review-board.md` |
| `spoon handoff` | Build `handoff.md` from accepted items |
| `spoon archive` | Archive task; requires `--archive-root`, `--project`, `--task` |
| `spoon run [--continue] [--json]` | Advance workflow by one phase |
| `spoon action list`, `complete`, `fail` | Host action queue |
| `spoon export-github` | Redacted export candidate directory |

## What Spoon Does Not Do

- Stage, commit, or push business code
- Read private chat logs or editor internals
- Auto-accept or auto-reject review findings

Final review judgment and Git operations remain yours. Generated implementation prompts can permit
coding-agent local checkpoint commits, but Spoon itself still does not perform Git writes.

## Related Docs

- [Design overview](design-overview.md)
- [Architecture](architecture.md) — Runner, gates, adapters, exit codes
- [Host actions](host-actions.md) — Codex, Cursor, Claude, manual contracts
- [GitHub export policy](export-policy.md)
- [Roadmap](roadmap.md)
