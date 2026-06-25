# Spoon Usage Guide

Spoon is a **local file workflow CLI**. It maintains Markdown and snapshot files under `.spoon/current/` in your business repository. It does **not** modify application code or create Git commits.

You, Cursor, Codex, and Claude Code read the same files. For automated phase advancement, use `spoon run` and the `spoon-orchestrator` Skill (see [architecture](architecture.md) and [host actions](host-actions.md)).

## Requirements

- Python 3.11 or newer
- Git
- A local checkout of [Spoon](https://github.com/charonwang/spoon)

## One-Time Install

Use **Python 3.11+ with pip**. On Windows, prefer the `py` launcher so you do not pick a `python` without pip.

> Examples use Windows PowerShell. On macOS/Linux, replace `\` path separators with `/` and use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

List installed interpreters, then verify the launcher tag works:

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

If `py -0p` lists 3.11 but `py -3.11 --version` fails, use the uv path below instead.

If `pip` is missing on the interpreter you chose:

```powershell
py -3.11 -m ensurepip --upgrade
py -3.11 -m pip install -e .
```

With [uv](https://docs.astral.sh/uv/) (recommended when `py -3.11 --version` fails):

```powershell
cd <spoon-checkout>
uv venv --python 3.11
uv pip install -e .
.\.venv\Scripts\activate
spoon --help
```

Without activating the venv:

```powershell
.\.venv\Scripts\python.exe -m spoon --help
```

If your default `python` already has pip:

```powershell
python -m pip install -e .
spoon --help
```

If `spoon` is not on your `PATH`, use `python -m spoon` instead.

After moving or cloning Spoon to a new path, reinstall with the same interpreter you used initially (for example `py -3.11 -m pip install -e .` or `uv pip install -e .` in the existing `.venv`).

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

Final review judgment and Git operations remain yours.

## Related Docs

- [Design overview](design-overview.md)
- [Architecture](architecture.md) — Runner, gates, adapters, exit codes
- [Host actions](host-actions.md) — Codex, Cursor, Claude, manual contracts
- [GitHub export policy](export-policy.md)
- [Roadmap](roadmap.md)
