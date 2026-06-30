# Spoon Design Overview

Spoon is a local workflow CLI for teams and solo developers who coordinate a task across multiple AI coding tools.

## Core Idea

Spoon keeps workflow state in regular files under `.spoon/current/`. Cursor, Codex, Claude Code, and humans read and update the same plan, review notes, handoff, and snapshots without a shared database or service.

A resumable **Runner** (`spoon run`) can advance workflow phases deterministically. Host tools execute actions the Runner cannot complete alone; the `spoon-orchestrator` Skill loops on `spoon run --json` and reports completion through `spoon action complete`.

## Boundaries

Spoon manages workflow artifacts only. It does not change application code, stage files, commit changes, push branches, or read private chat transcripts.

Implementation prompts may let a coding agent create local checkpoint commits after relevant
verification passes. Those commits are coding-agent recovery points; Spoon, the Runner, and host
actions still do not perform Git writes.

## Commands

Spoon provides file-workflow commands (`init`, `adopt-plan`, `snapshot`, `prompts`, `board`, `handoff`, `archive`) and orchestration commands (`run`, `action`, `export-github`).

Full command reference and day-to-day walkthrough: [usage.md](usage.md).

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
