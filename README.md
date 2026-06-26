# Spoon

[![CI](https://github.com/charonwang/spoon/actions/workflows/ci.yml/badge.svg)](https://github.com/charonwang/spoon/actions/workflows/ci.yml)

Spoon is a local Python CLI for coordinating planning, review, implementation handoff, and final checks across Cursor, Codex, and Claude Code.

It uses plain files as the shared source of truth. The tool creates and updates `.spoon/current/` in your target repository, then your editors and AI agents can read the same `brief.md`, `plan.md`, `review-board.md`, `handoff.md`, and snapshot files.

A resumable Runner (`spoon run`) can advance workflow phases; the `spoon-orchestrator` Skill executes host actions Codex and Cursor cannot run inside Python.

Spoon is intentionally local-first and conservative:

- It does not stage, commit, push, or modify business code.
- It does not read private chat logs or editor internals.
- It writes neutral Markdown, text, and JSON files that other tools can inspect.
- It assumes trusted local command input for `--test-cmd` and `--dependency-cmd`.

## Requirements

- Python 3.11 or newer
- Git

## Install

Spoon requires **Python 3.11+** (Python 3.12+ no longer bundles pip; use `ensurepip` or a virtual environment).

### With venv (recommended)

```powershell
cd <spoon-checkout>
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m spoon --help
```

### With uv

```powershell
cd <spoon-checkout>
uv venv --python ">=3.11"
uv pip install -e .
.\.venv\Scripts\python.exe -m spoon --help
```

### Global install with uv (recommended for daily use)

`uv tool install` puts `spoon` on your PATH (for example `~/.local/bin`) so it works from any directory without activating a venv:

```powershell
uv tool install -e <spoon-checkout>                     # editable: tracks your source
uv tool install <spoon-checkout>\dist\spoon-0.2.0-py3-none-any.whl  # or from a built wheel
spoon --help
```

Manage it later with `uv tool list`, `uv tool upgrade spoon`, and `uv tool uninstall spoon`. If `uv` is missing, install it with `irm https://astral.sh/uv/install.ps1 | iex`, then restart the terminal.

### If your Python already has pip

```powershell
cd <spoon-checkout>
python -m pip install -e .
spoon --help
```

### If pip is missing (Python 3.12+)

```powershell
cd <spoon-checkout>
python -m ensurepip --upgrade
python -m pip install -e .
spoon --help
```

More variants (py launcher, uv, PATH issues): see the [usage guide](docs/usage.md).

## Documentation

- [Usage guide](docs/usage.md) — install, workflow, and command reference
- [Design overview](docs/design-overview.md)
- [Architecture](docs/architecture.md) — Runner, gates, adapters, Skill loop
- [Roadmap](docs/roadmap.md) — release history and future work
- [Host actions](docs/host-actions.md) — Codex, Cursor, Claude, and manual contracts
- [GitHub export policy](docs/export-policy.md)

## Commands

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/`; exclude `.spoon/` from Git tracking |
| `spoon adopt-plan --source PATH` | Move a Cursor plan into `plan.md` |
| `spoon snapshot` | Capture Git status, diffs, tests, dependency checks |
| `spoon prompts` | Write reusable review and check prompts |
| `spoon board` | Summarize reviews into `review-board.md` |
| `spoon handoff` | Build `handoff.md` from accepted board items |
| `spoon archive` | Archive task (`--archive-root`, `--project`, `--task`) |
| `spoon run [--continue] [--json]` | Advance workflow one phase |
| `spoon action list`, `complete`, `fail` | Host action queue |
| `spoon export-github` | Redacted export candidate for GitHub history |

## Quick Start

Run Spoon from inside the Git repository you want to manage:

```powershell
spoon init
spoon adopt-plan --source "C:\path\to\cursor.plan.md"
spoon snapshot --test-cmd "python -m unittest discover -s tests -p \"test_*.py\""
spoon prompts
spoon board
spoon handoff
spoon run --json
spoon archive --archive-root "C:\path\to\archives" --project my-project --task my-task
```

## Workflow

1. Write a short task brief in `.spoon/current/brief.md`.
2. Create or revise a plan in Cursor, then move it into `.spoon/current/plan.md` with `spoon adopt-plan`.
3. Run `spoon snapshot` to capture Git status, diffs, recent commits, test output, dependency checks, and manual sensitive-scan notes.
4. Run `spoon prompts` to generate reusable prompts for Cursor, Codex, and Claude Code.
5. Put review files in `.spoon/current/reviews/`.
6. Run `spoon board` to summarize existing review files into `.spoon/current/review-board.md`.
7. Move accepted findings into the board's `Accepted For Handoff` section.
8. Run `spoon handoff` and give `.spoon/current/handoff.md` plus the plan to your coding agent.
9. Optionally use `spoon run` and `spoon action` to advance phases with host-tool help.
10. Run `spoon archive` when the task is complete.

## `.spoon/current/`

```text
.spoon/current/
  brief.md              # Human-written task brief and constraints
  plan.md               # Canonical implementation plan
  review-board.md       # Human decisions plus generated review summary
  handoff.md            # Accepted changes for the implementation agent
  metadata.json         # Local workflow metadata
  prompts/              # Reusable prompts for plan/code review and final checks
  reviews/              # Raw review notes from Cursor, Codex, Claude Code, etc.
  snapshots/            # Git status, diffs, command output, and related evidence
  run-state.json        # Runner phase (when using spoon run)
  actions.json          # Host action queue
  events.jsonl          # Append-only audit log
```

Spoon adds `.spoon/` to `.git/info/exclude` for the repository you run it in.

## Snapshot Notes

- `snapshots/status.txt` is the source for file state, including `??` untracked files.
- `snapshots/diff-stat.txt` and `snapshots/diff.patch` are split into unstaged, staged, and untracked sections.
- Untracked regular UTF-8 files up to 200 KB are included in `diff.patch`; binary, non-UTF-8, directory, or larger files are listed with a skip note.
- If `.spoon/current/metadata.json` is corrupt, `snapshot` rebuilds it and records `metadata_warning`.

## Cursor Link Format

Plans should use file URI links with line anchors:

```text
file:///C:/path/to/your/repo/internal/file.go#L82
```

Avoid raw Windows paths such as `C:\path\to\file.go:82`.

## Development

With venv (recommended):

```powershell
cd <spoon-checkout>
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python scripts/check_doc_links.py
```

With uv:

```powershell
uv venv --python ">=3.11"
uv pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts/check_doc_links.py
```

If pip is missing (Python 3.12+), bootstrap it first: `python -m ensurepip --upgrade`

## License

MIT. See [LICENSE](LICENSE).
