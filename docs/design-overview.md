# Spoon Design Overview

Spoon is a local **governance layer** for teams and solo developers who coordinate one
task across Cursor, Codex, and Claude Code. It owns shared plan / review / handoff
artifacts, human decision gates, and resumable phases — not parallel agent execution.

Product position and what not to become: [positioning.md](positioning.md).

## Core Idea

Spoon keeps workflow state in regular files under `.spoon/current/`. Cursor, Codex, Claude Code, and humans read and update the same plan, review notes, handoff, and snapshots without a shared database or service.

A resumable **Runner** (`spoon run`) can advance workflow phases deterministically. Host tools execute actions the Runner cannot complete alone; the `spoon` Skill loops on `spoon run --json` and reports completion through `spoon action complete`.

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
spoon Skill ← stateless host loop for Codex / Cursor / manual actions
```

Phase graph, gates, exit codes, and persistence rules: [architecture.md](architecture.md).

## Tradeoffs

- Path policy is optimized for Windows and Cursor Plan UI file links.
- Snapshot files are written sequentially; rerun `spoon snapshot` after interruptions.
- `--test-cmd` and `--dependency-cmd` are trusted local user input.
- Cursor UI automation is off by default (`experimental_cursor_ui` in `.spoon/config.json`).
- Prompt language defaults to the task request language (`language: "auto"`):
  follow `brief.md`, else `plan.md`, else English — same rule as host AGENTS.md.
  Override with an explicit tag such as `zh-CN` or `ja-JP`. Structural Spoon
  headings and severity tags stay English for the board parser.
- Optional per-agent overrides under `.spoon/config.json` → `agents`:
  `agents.claude.model`, `agents.codex.model`,
  `agents.codex.reasoning_effort` (`low` / `medium` / `high` / `xhigh` /
  `ultra` / `max` / …), and `agents.codex.service_tier` (for example
  `default` or `fast`). Enable surfaces with `agents.claude.cli`,
  `agents.codex.cli`, and `agents.codex.desktop`. When `visible_terminals` is
  true, Claude review display follows `terminal.launcher` (`windows_terminal`
  by default; also `conhost`, `tabby` (falls back on Windows), `custom`, `inline`). Conversation titles are
  `Spoon:<task_label>`: label comes from `spoon run --label`, else the first
  line of brief `## Goal`, persisted on `run-state.json` for the current
  requirement (one Claude/Codex conversation per run). Omit or null model
  fields to use each tool's own defaults. Unknown agent ids (for example
  future `pi`) are ignored until Spoon wires an adapter.

## Further Reading

- [Positioning](positioning.md) — governance-layer role vs multi-agent orchestrators
- [Architecture](architecture.md) — Runner, adapters, gates, Skill loop, export
- [Host actions](host-actions.md) — Codex, Cursor, Claude, and manual contracts
- [GitHub export policy](export-policy.md) — redacted export rules
- [Roadmap](roadmap.md) — release history and what comes next
