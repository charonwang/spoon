# Spoon Design Overview

Spoon is a local workflow CLI for teams and solo developers who coordinate a task across multiple AI coding tools.

## Core Idea

Spoon keeps workflow state in regular files under `.spoon/current/`. Cursor, Codex, Claude Code, and humans read and update the same plan, review notes, handoff, and snapshots without a shared database or service.

A resumable **Runner** (`spoon run`) can advance workflow phases deterministically. Host tools execute actions the Runner cannot complete alone; the `spoon-orchestrator` Skill loops on `spoon run --json` and reports completion through `spoon action complete`.

## Boundaries

Spoon manages workflow artifacts only. It does not change application code, stage files, commit changes, push branches, or read private chat transcripts.

## Commands

| Command | Purpose |
| --- | --- |
| `spoon init` | Create `.spoon/current/`; exclude `.spoon/` via `.git/info/exclude` |
| `spoon adopt-plan` | Move a Cursor plan into `plan.md` |
| `spoon snapshot` | Capture Git status, diffs, tests, dependency checks, sensitive-scan notes |
| `spoon prompts` | Write reusable review and check prompts |
| `spoon board` | Summarize raw reviews into `review-board.md` (preserves human decisions) |
| `spoon handoff` | Build implementation handoff from accepted board items |
| `spoon archive` | Archive the current task; recreate empty `current/` |
| `spoon run` | Advance workflow one phase; optional `--continue`, `--json` |
| `spoon action` | List, complete, or fail host actions |
| `spoon export-github` | Build redacted export candidate for review before GitHub push |

Day-to-day walkthrough: [usage.md](usage.md).

## Architecture (summary)

```text
.spoon/current/          ← files are source of truth (brief, plan, board, handoff, reviews, snapshots)
run-state.json           ← Runner phase and status
actions.json / events.jsonl ← action queue and audit log
adapters (Claude CLI)    ← in-process review execution
spoon-orchestrator Skill ← stateless host loop for Codex / Cursor / manual actions
```

Phase graph, gates, exit codes, and persistence rules: [architecture.md](architecture.md).

## Tradeoffs

- Path policy is optimized for Windows and Cursor Plan UI file links.
- Snapshot files are written sequentially; rerun `spoon snapshot` after interruptions.
- `--test-cmd` and `--dependency-cmd` are trusted local user input.
- Cursor UI automation is off by default (`experimental_cursor_ui` in `.spoon/config.json`).

## Further Reading

- [Architecture](architecture.md) — Runner, adapters, gates, Skill loop, export
- [Host actions](host-actions.md) — Codex, Cursor, Claude, and manual contracts
- [GitHub export policy](export-policy.md) — redacted export rules
- [Roadmap](roadmap.md) — release history and what comes next
- [Implementation plan](plans/v2-orchestrator-plan.md) — contributor task history
