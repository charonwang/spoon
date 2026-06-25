# Spoon Design Overview

Spoon is a local workflow CLI for teams and solo developers who coordinate a task across multiple AI coding tools.

## Core Idea

Spoon keeps the workflow state in regular files under `.spoon/current/`. Cursor, Codex, Claude Code, and humans can all read and update the same plan, review notes, handoff, and snapshots without requiring a shared database or service.

## Boundaries

Spoon manages workflow artifacts only. It does not change application code, stage files, commit changes, push branches, or read private chat transcripts.

## Main Commands

- `spoon init`: creates `.spoon/current/` and excludes `.spoon/` from Git tracking through `.git/info/exclude`.
- `spoon adopt-plan`: moves a Cursor plan into `.spoon/current/plan.md`.
- `spoon snapshot`: captures Git status, diffs, recent commits, test output, dependency checks, and sensitive-scan notes.
- `spoon prompts`: writes reusable prompts for plan review, code review, final checks, and commit-message drafting.
- `spoon board`: summarizes raw review files into generated findings while preserving human decisions.
- `spoon handoff`: writes an implementation handoff from accepted review-board items.
- `spoon archive`: archives the current task and recreates an empty `.spoon/current/`.

## V1 Tradeoffs

- The path policy is optimized for Windows and Cursor Plan UI file links.
- Snapshot files are written sequentially; rerun `spoon snapshot` after interruptions.
- `--test-cmd` and `--dependency-cmd` are trusted local user input.

## Using V1

See [v1-usage.md](v1-usage.md) for install steps, the full workflow, and command reference.

## V2 (planned)

V2 adds a resumable Runner (`spoon run`), host-action orchestration via the `spoon-orchestrator` Skill, Claude CLI adapters, and redacted `spoon export-github`. It does not change V1 file layout or boundaries.

- [Roadmap](roadmap.md) — phases, exit codes, non-goals
- [V2 architecture](v2-architecture.md) — components, phases, state files
- [Host actions](host-actions.md) — host execution and manual fallback contract
- [GitHub export policy](export-policy.md) — redacted export rules
- [Implementation plan](plans/v2-orchestrator-plan.md) — task list for contributors
