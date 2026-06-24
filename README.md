# Spoon

[![CI](https://github.com/charonwang/spoon/actions/workflows/ci.yml/badge.svg)](https://github.com/charonwang/spoon/actions/workflows/ci.yml)

Spoon is a local Python CLI for coordinating planning, review, implementation handoff, and final checks across Cursor, Codex, and Claude Code.

It uses plain files as the shared source of truth. The tool creates and updates `.spoon/current/` in your target repository, then your editors and AI agents can read the same `brief.md`, `plan.md`, `review-board.md`, `handoff.md`, and snapshot files.

## Status

**V1 (`v0.1.x`)** — file-based CLI; commands below are available today.

**V2 (planned)** — Runner, orchestrator Skill, and GitHub export. Design docs only until a V2 release; see [Roadmap](docs/roadmap.md).

Spoon is intentionally local-first and conservative:

- It does not stage, commit, push, or modify business code.
- It does not read private chat logs or editor internals.
- It writes neutral Markdown, text, and JSON files that other tools can inspect.
- It assumes trusted local command input for `--test-cmd` and `--dependency-cmd`.

## Requirements

- Python 3.11 or newer
- Git

## Install

From a local checkout:

```powershell
python -m pip install -e .
```

After editable install:

```powershell
spoon init
```

For one-off source-tree execution without installation, set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH = "src"
python -m spoon init
```

## Documentation

- [V1 usage guide](docs/v1-usage.md) — install, workflow, and commands for day-to-day use
- [Design overview](docs/design-overview.md)
- [Roadmap](docs/roadmap.md) — V2 plans

## Quick Start

Run Spoon from inside the Git repository you want to manage:

```powershell
spoon init
spoon adopt-plan --source "C:\path\to\cursor.plan.md"
spoon snapshot --test-cmd "python -m unittest discover -s tests -p \"test_*.py\""
spoon prompts
spoon board
spoon handoff
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
9. Run `spoon archive` when the task is complete.

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
```

Spoon adds `.spoon/` to `.git/info/exclude` for the repository you run it in. This keeps local workflow state out of your project commits without editing the repository's `.gitignore`.

## Snapshot Notes

- `snapshots/status.txt` is the source for file state, including `??` untracked files.
- `snapshots/diff-stat.txt` and `snapshots/diff.patch` are split into unstaged, staged, and untracked sections.
- Untracked regular UTF-8 files up to 200 KB are included in `diff.patch`; binary, non-UTF-8, directory, or larger files are listed with a skip note.
- `snapshot` writes files sequentially, not transactionally; if it is interrupted or a command fails mid-run, rerun `snapshot` to refresh every file.
- If `.spoon/current/metadata.json` is corrupt, `snapshot` rebuilds it and records `metadata_warning`.

## Cursor Link Format

Spoon's V1 path policy is optimized for Windows and Cursor Plan UI links. Plans should use file URI links with line anchors:

```text
file:///C:/path/to/your/repo/internal/file.go#L82
```

Avoid raw Windows paths such as:

```text
C:\path\to\file.go:82
C:/path/to/file.go:82
```

## Migrating From Old `.ai-flow/` Drafts

If you used an early local draft of this workflow, rename the directory in each business repository:

```powershell
Rename-Item .ai-flow .spoon
```

Then update `.git/info/exclude` in that repository so it contains:

```text
.spoon/
```

No dual compatibility is planned for V1.

## Roadmap

| Version | Focus |
| --- | --- |
| V1 (current) | `init` … `archive`, `.spoon/current/` file workflow |
| V2A | Runner, `spoon run`, `spoon action` |
| V2B | Claude CLI adapter |
| V2C | `spoon-orchestrator` Skill |
| V2D | `spoon export-github` + history validation template |

Details: [docs/roadmap.md](docs/roadmap.md), [docs/v2-architecture.md](docs/v2-architecture.md), [docs/plans/v2-orchestrator-plan.md](docs/plans/v2-orchestrator-plan.md).

## Development

Install the project in editable mode before running tests:

```powershell
python -m pip install -e .
```

Run the full test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## License

MIT. See [LICENSE](LICENSE).
